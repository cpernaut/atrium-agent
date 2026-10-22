"""F-03 · Presupuesto y gastos: data access and calculations.

Tables ``rubros``, ``presupuesto_items`` and ``gastos`` (see
``supabase_schema.sql``). Same pattern as ``atrium.obras``: functions that take
the signed-in user's Supabase client (so RLS applies) and raise
``FinanzasError`` with messages ready to show.

Money rules (docs/producto/funcionalidades/F-03-presupuesto-gastos.md):
amounts are stored in their own currency and never rewritten; each row keeps
the MEP average of its date (``tipo_cambio``, origin ``auto`` or ``manual``);
conversions use that rate, and a row without a rate is never converted.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from atrium import cotizaciones
from atrium.obras import MONEDAS

if TYPE_CHECKING:
    from supabase import Client

# Same list and order as the precarga in supabase_schema.sql (a test checks it).
RUBROS_INICIALES = (
    ("Trabajos preliminares", 10),
    ("Movimiento de suelo", 20),
    ("Fundaciones", 30),
    ("Estructura", 40),
    ("Steel frame", 50),
    ("Mampostería", 60),
    ("Cubierta", 70),
    ("Instalación sanitaria", 80),
    ("Instalación eléctrica", 90),
    ("Instalación de gas", 100),
    ("Revoques", 110),
    ("Contrapisos y carpetas", 120),
    ("Pisos y revestimientos", 130),
    ("Carpinterías", 140),
    ("Pintura", 150),
    ("Honorarios y trámites", 160),
    ("Limpieza final", 170),
    ("Otros", 999),
)

ORIGEN_AUTO = "auto"
ORIGEN_MANUAL = "manual"
TABLAS_CON_COTIZACION = ("gastos", "presupuesto_items")

# Limits mirror the database (numeric(14,2), numeric(12,4) and text checks).
_MONTO_MAX = Decimal("999999999999.99")
_TC_MAX = Decimal("99999999.9999")
_DESCRIPCION_MAX = 200
_PROVEEDOR_MAX = 120
_RUBRO_MIN, _RUBRO_MAX = 2, 60
_CENTAVOS = Decimal("0.01")

# Argentina has no daylight saving time: a fixed offset is exact and needs no tzdata.
_ARGENTINA = timezone(timedelta(hours=-3))

Fila = dict[str, Any]


class FinanzasError(RuntimeError):
    """Invalid input or a failed read/write; the message is ready to show."""


def hoy() -> date:
    """Today in Argentina (the server runs in UTC)."""

    return datetime.now(_ARGENTINA).date()


_PAGINA = 1000  # Supabase's default max rows per response
_MAX_PAGINAS = 200  # 200.000 rows: far beyond any obra; guards against loops


def _run_all(build) -> list[Fila]:
    """Every row of a query, page by page.

    ``build`` returns a fresh query with a stable order (ending in ``id``).
    Pages advance by the rows actually received, so a server with a smaller
    max-rows setting can't make us stop early and silently drop rows.
    """

    filas: list[Fila] = []
    for _ in range(_MAX_PAGINAS):
        pagina = _run(build().range(len(filas), len(filas) + _PAGINA - 1))
        if not pagina:
            return filas
        filas.extend(pagina)
    raise FinanzasError("Hay demasiados registros para calcular el resumen.")


def _run(query) -> list[Fila]:
    try:
        return query.execute().data or []
    except Exception as exc:  # noqa: BLE001 - wrap the provider error
        mensaje = str(exc)
        if "rubros_nombre_clave_unico" in mensaje or "duplicate key" in mensaje:
            raise FinanzasError("Ya existe un rubro con ese nombre.") from exc
        raise FinanzasError(mensaje) from exc


# --------------------------------------------------------------------------- #
# Parsing and validation
# --------------------------------------------------------------------------- #
_MILES_AR = re.compile(r"^[1-9]\d{0,2}(\.\d{3})+$")  # "350.000"; never "0.001"


def parse_decimal(valor: Any) -> Decimal:
    """Number from a form, the agent or the database.

    Accepts Argentine formats too: ``"350.000"``, ``"1.234,50"``, ``"1234,5"``.
    """

    if isinstance(valor, Decimal):
        numero = valor
    elif isinstance(valor, bool) or valor is None:
        raise FinanzasError("Falta el número.")
    elif isinstance(valor, (int, float)):
        numero = Decimal(str(valor))
    else:
        texto = str(valor).strip().replace(" ", "").replace("$", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif _MILES_AR.match(texto):
            texto = texto.replace(".", "")
        try:
            numero = Decimal(texto)
        except InvalidOperation as exc:
            raise FinanzasError(f"«{valor}» no es un número válido.") from exc
    if not numero.is_finite():
        raise FinanzasError("El número no es válido.")
    return numero


def _en_rango(valor: Any, paso: Decimal, maximo: Decimal, que: str) -> Decimal:
    """Round to ``paso`` only after checking the range (huge values can't be rounded)."""

    numero = parse_decimal(valor)
    if numero <= 0:
        raise FinanzasError(f"{que} tiene que ser mayor que cero.")
    if numero > maximo:
        raise FinanzasError(f"{que} es demasiado grande.")
    redondeado = numero.quantize(paso, rounding=ROUND_HALF_UP)
    if redondeado <= 0:
        raise FinanzasError(f"{que} tiene que ser mayor que cero.")
    return redondeado


def parse_monto(valor: Any) -> Decimal:
    return _en_rango(valor, _CENTAVOS, _MONTO_MAX, "El monto")


def parse_tipo_cambio(valor: Any) -> Decimal:
    return _en_rango(valor, Decimal("0.0001"), _TC_MAX, "El tipo de cambio")


def _moneda(valor: Any) -> str:
    moneda = str(valor or "").strip().upper()
    if moneda in ("$", "PESOS", "PESO"):
        moneda = "ARS"
    if moneda in ("U$S", "US$", "DOLARES", "DÓLARES", "DOLAR", "DÓLAR"):
        moneda = "USD"
    if moneda not in MONEDAS:
        raise FinanzasError(f"Moneda inválida: {valor}. Opciones: {', '.join(MONEDAS)}.")
    return moneda


def _texto(valor: Any, campo: str, maximo: int, obligatorio: bool) -> str | None:
    texto = " ".join(str(valor or "").split())
    if not texto:
        if obligatorio:
            raise FinanzasError(f"Falta {campo}.")
        return None
    if len(texto) > maximo:
        raise FinanzasError(f"{campo.capitalize()} puede tener hasta {maximo} caracteres.")
    return texto


def _fecha(valor: date | str | None) -> date:
    if valor is None or valor == "":
        return hoy()
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor).strip())
    except ValueError as exc:
        raise FinanzasError(f"Fecha inválida: {valor}. Usá el formato AAAA-MM-DD.") from exc


def normalizar(texto: str) -> str:
    """Lowercase, no accents, single spaces: for comparing names."""

    sin_tildes = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return " ".join(sin_tildes.lower().split())


# --------------------------------------------------------------------------- #
# Rubros
# --------------------------------------------------------------------------- #
def list_rubros(client: Client, incluir_inactivos: bool = False) -> list[Fila]:
    def build():
        query = client.table("rubros").select("*").order("orden").order("nombre").order("id")
        return query if incluir_inactivos else query.eq("activo", True)

    return _run_all(build)


def find_rubros(client: Client, texto: str) -> list[Fila]:
    """Active rubros matching ``texto``: exact name first, else partial match."""

    buscado = normalizar(texto or "")
    if not buscado:
        return []
    rubros = list_rubros(client)
    exactos = [r for r in rubros if normalizar(r["nombre"]) == buscado]
    return exactos or [r for r in rubros if buscado in normalizar(r["nombre"])]


def create_rubro(client: Client, nombre: str, orden: int | None = None) -> Fila:
    """Add a rubro to the shared list.

    Ready for the next iteration (no screen yet). Names are unique ignoring
    case, accents and extra spaces.
    """

    limpio = _texto(nombre, "el nombre del rubro", _RUBRO_MAX, obligatorio=True)
    if len(limpio) < _RUBRO_MIN:
        raise FinanzasError(f"El nombre del rubro necesita al menos {_RUBRO_MIN} caracteres.")
    existentes = list_rubros(client, incluir_inactivos=True)
    for rubro in existentes:
        if normalizar(rubro["nombre"]) == normalizar(limpio):
            estado = "" if rubro.get("activo", True) else " (está desactivado)"
            raise FinanzasError(f"Ya existe el rubro «{rubro['nombre']}»{estado}.")
    if orden is None:
        # Before "Otros" (999), after everything else.
        ordenes = [r.get("orden", 0) for r in existentes if r.get("orden", 0) < 999]
        orden = min(max(ordenes, default=0) + 10, 998)
    try:
        orden = int(orden)
    except (TypeError, ValueError) as exc:
        raise FinanzasError("El orden del rubro tiene que ser un número.") from exc
    if not 0 <= orden <= 100000:
        raise FinanzasError("El orden del rubro no es válido.")
    filas = _run(client.table("rubros").insert({"nombre": limpio, "orden": orden}))
    return filas[0] if filas else {"nombre": limpio, "orden": orden}


def set_rubro_activo(client: Client, rubro_id: int, activo: bool) -> Fila:
    """Deactivate (or reactivate) a rubro instead of deleting it."""

    filas = _run(client.table("rubros").update({"activo": bool(activo)}).eq("id", rubro_id))
    if not filas:
        raise FinanzasError("No se encontró el rubro.")
    return filas[0]


def _rubro_activo(client: Client, rubro_id: Any) -> Fila:
    try:
        rubro_id = int(rubro_id)
    except (TypeError, ValueError) as exc:
        raise FinanzasError("Elegí un rubro.") from exc
    filas = _run(client.table("rubros").select("*").eq("id", rubro_id).limit(1))
    if not filas:
        raise FinanzasError("El rubro elegido no existe.")
    if not filas[0].get("activo", True):
        raise FinanzasError(f"El rubro «{filas[0]['nombre']}» está desactivado.")
    return filas[0]


# --------------------------------------------------------------------------- #
# Cotización
# --------------------------------------------------------------------------- #
def cotizar(fecha: date) -> tuple[Decimal | None, str | None, str | None]:
    """(tipo_cambio, origen, aviso) for a new row dated ``fecha``.

    Never raises: if the MEP can't be obtained the row is saved without a rate
    and ``aviso`` explains it (F-03 R3).
    """

    try:
        tc = cotizaciones.mep_promedio(fecha)
        if tc is not None:
            tc = parse_tipo_cambio(tc)  # an absurd value from the source must not block saving
    except (cotizaciones.CotizacionError, FinanzasError):
        return (
            None,
            None,
            (
                "No se pudo consultar el dólar MEP en este momento: se guardó sin "
                "cotización. Podés cargarla a mano más tarde."
            ),
        )
    if tc is None:
        return (
            None,
            None,
            (
                f"No hay cotización del dólar MEP para el {fecha:%d/%m/%Y}: se guardó sin "
                "cotización. Podés cargarla a mano."
            ),
        )
    return tc, ORIGEN_AUTO, None


def _con_cotizacion(fila: Fila, fecha: date, tipo_cambio: Any) -> str | None:
    if tipo_cambio not in (None, "", 0):
        fila["tipo_cambio"] = str(parse_tipo_cambio(tipo_cambio))
        fila["tipo_cambio_origen"] = ORIGEN_MANUAL
        return None
    tc, origen, aviso = cotizar(fecha)
    if tc is not None:
        fila["tipo_cambio"] = str(tc)
        fila["tipo_cambio_origen"] = origen
    return aviso


def set_tipo_cambio(client: Client, tabla: str, fila_id: int, valor: Any) -> Fila:
    """Manual correction of the rate; it is never overwritten automatically."""

    if tabla not in TABLAS_CON_COTIZACION:
        raise FinanzasError("Tabla inválida.")
    cambios = {"tipo_cambio": str(parse_tipo_cambio(valor)), "tipo_cambio_origen": ORIGEN_MANUAL}
    filas = _run(client.table(tabla).update(cambios).eq("id", fila_id))
    if not filas:
        raise FinanzasError("No se encontró el registro.")
    return filas[0]


# --------------------------------------------------------------------------- #
# Gastos
# --------------------------------------------------------------------------- #
def add_gasto(
    client: Client,
    obra_id: int,
    *,
    monto: Any,
    moneda: str,
    rubro_id: Any,
    descripcion: str,
    fecha: date | str | None = None,
    proveedor: str | None = None,
    tipo_cambio: Any = None,
) -> tuple[Fila, str | None]:
    """Insert a gasto. Returns (row, aviso); ``aviso`` is set when no rate was found."""

    fecha_gasto = _fecha(fecha)
    if fecha_gasto > hoy():
        raise FinanzasError("La fecha del gasto no puede ser futura.")
    fila: Fila = {
        "obra_id": int(obra_id),
        "fecha": fecha_gasto.isoformat(),
        "monto": str(parse_monto(monto)),
        "moneda": _moneda(moneda),
        "rubro_id": _rubro_activo(client, rubro_id)["id"],
        "descripcion": _texto(descripcion, "la descripción", _DESCRIPCION_MAX, True),
        "proveedor": _texto(proveedor, "el proveedor", _PROVEEDOR_MAX, False),
    }
    aviso = _con_cotizacion(fila, fecha_gasto, tipo_cambio)
    filas = _run(client.table("gastos").insert(fila))
    return (filas[0] if filas else fila), aviso


def list_gastos(client: Client, obra_id: int, limit: int | None = None) -> list[Fila]:
    """All gastos of the obra, newest first (``limit`` only for short listings)."""

    def build():
        return (
            client.table("gastos")
            .select("*")
            .eq("obra_id", obra_id)
            .order("fecha", desc=True)
            .order("created_at", desc=True)
            .order("id", desc=True)
        )

    if limit:
        return _run(build().limit(limit))
    return _run_all(build)


def anular_gasto(client: Client, gasto_id: int) -> Fila:
    filas = _run(client.table("gastos").update({"anulado": True}).eq("id", gasto_id))
    if not filas:
        raise FinanzasError("No se encontró el gasto.")
    return filas[0]


# --------------------------------------------------------------------------- #
# Presupuesto
# --------------------------------------------------------------------------- #
def add_presupuesto_item(
    client: Client,
    obra_id: int,
    *,
    monto: Any,
    moneda: str,
    rubro_id: Any,
    descripcion: str | None = None,
    tipo_cambio: Any = None,
) -> tuple[Fila, str | None]:
    """Insert a budget item dated today, with today's MEP (F-03 D7)."""

    fecha = hoy()
    fila: Fila = {
        "obra_id": int(obra_id),
        "fecha": fecha.isoformat(),
        "monto": str(parse_monto(monto)),
        "moneda": _moneda(moneda),
        "rubro_id": _rubro_activo(client, rubro_id)["id"],
        "descripcion": _texto(descripcion, "la descripción", _DESCRIPCION_MAX, False),
    }
    aviso = _con_cotizacion(fila, fecha, tipo_cambio)
    filas = _run(client.table("presupuesto_items").insert(fila))
    return (filas[0] if filas else fila), aviso


def list_presupuesto(client: Client, obra_id: int) -> list[Fila]:
    def build():
        return (
            client.table("presupuesto_items")
            .select("*")
            .eq("obra_id", obra_id)
            .order("created_at")
            .order("id")
        )

    return _run_all(build)


def anular_presupuesto_item(client: Client, item_id: int) -> Fila:
    filas = _run(client.table("presupuesto_items").update({"anulado": True}).eq("id", item_id))
    if not filas:
        raise FinanzasError("No se encontró el ítem del presupuesto.")
    return filas[0]


# --------------------------------------------------------------------------- #
# Conversion and summary
# --------------------------------------------------------------------------- #
def convertir(monto: Any, moneda: str, tipo_cambio: Any, destino: str) -> Decimal | None:
    """Amount in ``destino`` using the row's own rate; None if it can't be converted."""

    valor = parse_decimal(monto)
    if moneda == destino:
        return valor
    if tipo_cambio in (None, ""):
        return None
    tc = parse_decimal(tipo_cambio)
    if tc <= 0:
        return None
    return valor * tc if destino == "ARS" else valor / tc


@dataclass
class FilaResumen:
    rubro_id: int
    rubro: str
    presupuestado: Decimal = Decimal(0)
    gastado: Decimal = Decimal(0)

    @property
    def desvio(self) -> Decimal:
        """Gastado − presupuestado: positive means over budget."""

        return self.gastado - self.presupuestado

    @property
    def ejecutado(self) -> Decimal | None:
        """Share of the budget spent (1 = 100%); None without budget."""

        return self.gastado / self.presupuestado if self.presupuestado > 0 else None


@dataclass
class Resumen:
    moneda: str
    filas: list[FilaResumen] = field(default_factory=list)
    # Rows that count but have no rate to convert into ``moneda``.
    sin_convertir: list[Fila] = field(default_factory=list)

    @property
    def presupuestado(self) -> Decimal:
        return sum((f.presupuestado for f in self.filas), Decimal(0))

    @property
    def gastado(self) -> Decimal:
        return sum((f.gastado for f in self.filas), Decimal(0))

    @property
    def desvio(self) -> Decimal:
        return self.gastado - self.presupuestado

    @property
    def ejecutado(self) -> Decimal | None:
        return self.gastado / self.presupuestado if self.presupuestado > 0 else None

    @property
    def incompleto(self) -> bool:
        return bool(self.sin_convertir)


def calcular_resumen(
    items: Iterable[Fila],
    gastos: Iterable[Fila],
    rubros: Iterable[Fila],
    moneda: str,
) -> Resumen:
    """Budget vs. spending per rubro in ``moneda`` (pure function, no I/O)."""

    moneda = _moneda(moneda)
    info = {r["id"]: r for r in rubros}
    filas: dict[int, FilaResumen] = {}
    resumen = Resumen(moneda=moneda)

    def acumular(fila: Fila, campo: str) -> None:
        if fila.get("anulado"):
            return
        valor = convertir(fila["monto"], fila["moneda"], fila.get("tipo_cambio"), moneda)
        if valor is None:
            resumen.sin_convertir.append(fila)
            return
        rubro_id = fila["rubro_id"]
        nombre = info.get(rubro_id, {}).get("nombre", f"Rubro #{rubro_id}")
        destino = filas.setdefault(rubro_id, FilaResumen(rubro_id, nombre))
        setattr(destino, campo, getattr(destino, campo) + valor)

    for item in items:
        acumular(item, "presupuestado")
    for gasto in gastos:
        acumular(gasto, "gastado")

    resumen.filas = sorted(
        filas.values(),
        key=lambda f: (info.get(f.rubro_id, {}).get("orden", 10**6), normalizar(f.rubro)),
    )
    return resumen


def resumen(client: Client, obra_id: int, moneda: str) -> Resumen:
    return calcular_resumen(
        list_presupuesto(client, obra_id),
        list_gastos(client, obra_id),
        list_rubros(client, incluir_inactivos=True),
        moneda,
    )


# --------------------------------------------------------------------------- #
# Formatting (es-AR)
# --------------------------------------------------------------------------- #
def formato_numero(valor: Any, decimales: int | None = None) -> str:
    """``1800000`` -> ``"1.800.000"``; ``1500.5`` -> ``"1.500,50"``."""

    numero = parse_decimal(valor)
    if decimales is None:
        decimales = 0 if numero == numero.to_integral_value() else 2
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def formato_monto(valor: Any, moneda: str) -> str:
    numero = parse_decimal(valor).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)
    signo = "−" if numero < 0 else ""
    return f"{signo}{moneda} {formato_numero(abs(numero))}"


def formato_porcentaje(fraccion: Decimal | None) -> str:
    if fraccion is None:
        return "sin presupuesto"
    return f"{formato_numero((fraccion * 100).quantize(Decimal(1)), 0)}%"


def estado_desvio(desvio: Decimal, presupuestado: Decimal) -> str:
    """Plain-language status, so meaning never depends on color alone."""

    if presupuestado <= 0:
        return "Sin presupuesto"
    if desvio > 0:
        return "Excedido"
    return "Dentro del presupuesto"


def describe_resumen(res: Resumen, nombre_obra: str) -> str:
    """Prompt-ready summary for the agent."""

    m = res.moneda
    estado_total = estado_desvio(res.desvio, res.presupuestado)
    lineas = [
        f"Plata de {nombre_obra} en {m}:",
        f"- Presupuestado: {formato_monto(res.presupuestado, m)}",
        f"- Gastado: {formato_monto(res.gastado, m)}",
        f"- Desvío: {formato_monto(res.desvio, m)} ({estado_total})",
        "Por rubro:",
    ]
    for f in res.filas:
        lineas.append(
            f"- {f.rubro}: presupuestado {formato_monto(f.presupuestado, m)}, gastado "
            f"{formato_monto(f.gastado, m)}, desvío {formato_monto(f.desvio, m)}, "
            f"ejecutado {formato_porcentaje(f.ejecutado)} "
            f"({estado_desvio(f.desvio, f.presupuestado)})"
        )
    if not res.filas:
        lineas.append("- (no hay presupuesto ni gastos cargados)")
    if res.incompleto:
        lineas.append(
            f"ATENCIÓN: {len(res.sin_convertir)} registro(s) sin cotización no se pudieron "
            f"convertir a {m}; el total está incompleto."
        )
    return "\n".join(lineas)
