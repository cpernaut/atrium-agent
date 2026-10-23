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
        if "presupuesto_items_un_imprevistos" in mensaje:
            raise FinanzasError("Esta obra ya tiene un ítem de imprevistos.") from exc
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


def _en_rango(valor: Any, paso: Decimal, maximo: Decimal, que: str, cero: bool = False) -> Decimal:
    """Round to ``paso`` only after checking the range (huge values can't be rounded).

    ``cero``: zero is allowed (budget items, #35 D9); negatives never are.
    """

    numero = parse_decimal(valor)
    if numero < 0 or (numero == 0 and not cero):
        raise FinanzasError(
            f"{que} no puede ser negativo." if cero else f"{que} tiene que ser mayor que cero."
        )
    if numero > maximo:
        raise FinanzasError(f"{que} es demasiado grande.")
    redondeado = numero.quantize(paso, rounding=ROUND_HALF_UP)
    if redondeado <= 0 and not cero:
        raise FinanzasError(f"{que} tiene que ser mayor que cero.")
    return redondeado


def parse_monto(valor: Any) -> Decimal:
    """Amount of a gasto: always greater than zero."""

    return _en_rango(valor, _CENTAVOS, _MONTO_MAX, "El monto")


def parse_monto_item(valor: Any) -> Decimal:
    """Amount of a budget item: zero or empty is fine, values come later (#35 D9)."""

    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return Decimal("0.00")
    return _en_rango(valor, _CENTAVOS, _MONTO_MAX, "El monto", cero=True)


def parse_tipo_cambio(valor: Any) -> Decimal:
    return _en_rango(valor, Decimal("0.0001"), _TC_MAX, "El tipo de cambio")


def _moneda(valor: Any) -> str:
    moneda = str(valor or "").strip().upper()
    if not moneda:
        raise FinanzasError("Elegí la moneda.")
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
    """Deactivate (or reactivate) a rubro instead of deleting it.

    «Otros» always stays active: every new obra's «Imprevistos» goes there.
    """

    if not activo:
        filas = _run(client.table("rubros").select("*").eq("id", rubro_id).limit(1))
        if filas and normalizar(filas[0]["nombre"]) == "otros":
            raise FinanzasError(
                "«Otros» no se puede desactivar: ahí va el ítem «Imprevistos» de cada obra."
            )
    filas = _run(client.table("rubros").update({"activo": bool(activo)}).eq("id", rubro_id))
    if not filas:
        raise FinanzasError("No se encontró el rubro.")
    return filas[0]


def mover_rubro(client: Client, rubro_id: int, paso: int) -> list[Fila]:
    """Move a rubro one place up (``paso=-1``) or down (``paso=1``) in the list.

    The order is the one every screen and the budget table use. Rubros with the
    same ``orden`` are first renumbered (in steps of 10) so the move is visible.
    Returns the rubros whose ``orden`` changed.
    """

    if paso not in (-1, 1):
        raise FinanzasError("Solo se puede mover un lugar para arriba o para abajo.")
    rubros = list_rubros(client, incluir_inactivos=True)
    ids = [r["id"] for r in rubros]
    if rubro_id not in ids:
        raise FinanzasError("No se encontró el rubro.")
    i = ids.index(rubro_id)
    j = i + paso
    if not 0 <= j < len(rubros):
        return []
    ordenes = [int(r.get("orden") or 0) for r in rubros]
    if len(set(ordenes)) != len(ordenes):
        ordenes = [(k + 1) * 10 for k in range(len(rubros))]
    ordenes[i], ordenes[j] = ordenes[j], ordenes[i]
    cambiados = []
    for rubro, orden in zip(rubros, ordenes, strict=True):
        if int(rubro.get("orden") or 0) != orden:
            filas = _run(client.table("rubros").update({"orden": orden}).eq("id", rubro["id"]))
            cambiados.append(filas[0] if filas else {**rubro, "orden": orden})
    return cambiados


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
    presupuesto_item_id: Any,
    *,
    monto: Any,
    moneda: str,
    descripcion: str,
    fecha: date | str | None = None,
    proveedor: str | None = None,
    tipo_cambio: Any = None,
    proveedor_id: Any = None,
) -> tuple[Fila, str | None]:
    """Insert a gasto of a budget item (#35 R11). Returns (row, aviso).

    ``proveedor_id`` is a proveedor of the shared list (#37); its name is also
    kept in ``proveedor`` (the old free-text column).

    The obra and the rubro come from the item (the database enforces it too);
    ``aviso`` is set when no rate was found.
    """

    try:
        item_id = int(presupuesto_item_id)
    except (TypeError, ValueError) as exc:
        raise FinanzasError("Elegí el ítem del presupuesto.") from exc
    item = get_presupuesto_item(client, item_id)
    if item.get("anulado"):
        raise FinanzasError("Este ítem fue borrado: no se le pueden agregar gastos.")
    rubros = _run(client.table("rubros").select("*").eq("id", int(item["rubro_id"])).limit(1))
    if rubros and not rubros[0].get("activo", True):
        # R7: a deactivated rubro takes no new loads; the item's history stays.
        raise FinanzasError(
            f"El rubro «{rubros[0]['nombre']}» está desactivado: para cargarle gastos, "
            "cambiá el ítem a un rubro activo con «Editar ítem»."
        )
    fecha_gasto = _fecha(fecha)
    if fecha_gasto > hoy():
        raise FinanzasError("La fecha del gasto no puede ser futura.")
    fila: Fila = {
        "presupuesto_item_id": item_id,
        "obra_id": int(item["obra_id"]),
        "rubro_id": int(item["rubro_id"]),
        "fecha": fecha_gasto.isoformat(),
        "monto": str(parse_monto(monto)),
        "moneda": _moneda(moneda),
        "descripcion": _texto(descripcion, "la descripción", _DESCRIPCION_MAX, True),
        "proveedor": _texto(proveedor, "el proveedor", _PROVEEDOR_MAX, False),
    }
    if proveedor_id not in (None, ""):
        elegido = _proveedor_vigente(client, proveedor_id)
        fila["proveedor_id"] = elegido["id"]
        fila["proveedor"] = elegido["nombre"]
    aviso = _con_cotizacion(fila, fecha_gasto, tipo_cambio)
    filas = _run(client.table("gastos").insert(fila))
    return (filas[0] if filas else fila), aviso


def _proveedor_vigente(client: Client, proveedor_id: Any) -> Fila:
    """A proveedor of the list that can be chosen (not eliminated)."""

    try:
        proveedor_id = int(proveedor_id)
    except (TypeError, ValueError) as exc:
        raise FinanzasError("Elegí un proveedor de la lista.") from exc
    filas = _run(client.table("proveedores").select("*").eq("id", proveedor_id).limit(1))
    if not filas:
        raise FinanzasError("El proveedor elegido no existe.")
    if filas[0].get("archivado"):
        raise FinanzasError(f"El proveedor «{filas[0]['nombre']}» fue eliminado: elegí otro.")
    return filas[0]


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


def get_gasto(client: Client, gasto_id: int) -> Fila:
    filas = _run(client.table("gastos").select("*").eq("id", int(gasto_id)).limit(1))
    if not filas:
        raise FinanzasError("No se encontró el gasto.")
    return filas[0]


# Only these columns of a gasto can change (#25). The database enforces the same
# list with column privileges: obra, author and creation date never change.
CAMPOS_EDITABLES_GASTO = (
    "presupuesto_item_id",
    "fecha",
    "descripcion",
    "proveedor",
    "proveedor_id",
    "monto",
    "moneda",
    "tipo_cambio",
    "tipo_cambio_origen",
)


def update_gasto(
    client: Client,
    gasto_id: int,
    *,
    presupuesto_item_id: Any,
    fecha: date | str | None,
    monto: Any,
    moneda: str,
    descripcion: str,
    proveedor: str | None = None,
    tipo_cambio: Any = None,
    proveedor_id: Any = None,
) -> tuple[Fila, str | None]:
    """Edit every field of a gasto (#25). Returns (row, aviso).

    ``proveedor_id``: the proveedor of the list (#37), or None for none. A gasto
    keeps an eliminated proveedor it already had, but can't be moved to one.

    - It can move to another vigent item of the same obra (rubro follows the item).
    - ``tipo_cambio``: a different value replaces the rate and marks it ``manual``.
      Otherwise a manual rate is kept, and an automatic one (or none) is looked up
      again for the new date when the date changes (or when there was none).
    - A cancelled (anulado) gasto can't be edited.
    """

    actual = get_gasto(client, gasto_id)
    if actual.get("anulado"):
        raise FinanzasError("Este gasto está anulado: ya no se puede editar.")
    try:
        item_id = int(presupuesto_item_id)
    except (TypeError, ValueError) as exc:
        raise FinanzasError("Elegí el ítem del presupuesto.") from exc
    item = get_presupuesto_item(client, item_id)
    if item_id != actual.get("presupuesto_item_id"):
        if item.get("anulado"):
            raise FinanzasError("Ese ítem fue borrado: elegí otro.")
        if int(item["obra_id"]) != int(actual["obra_id"]):
            raise FinanzasError("Ese ítem es de otra obra.")
        rubros = _run(client.table("rubros").select("*").eq("id", int(item["rubro_id"])).limit(1))
        if rubros and not rubros[0].get("activo", True):
            raise FinanzasError(
                f"El rubro «{rubros[0]['nombre']}» está desactivado: elegí un ítem de otro rubro."
            )
    fecha_gasto = _fecha(fecha)
    if fecha_gasto > hoy():
        raise FinanzasError("La fecha del gasto no puede ser futura.")

    cambios: Fila = {
        "presupuesto_item_id": item_id,
        "fecha": fecha_gasto.isoformat(),
        "monto": str(parse_monto(monto)),
        "moneda": _moneda(moneda),
        "descripcion": _texto(descripcion, "la descripción", _DESCRIPCION_MAX, True),
        "proveedor": _texto(proveedor, "el proveedor", _PROVEEDOR_MAX, False),
        "proveedor_id": None,
    }
    if proveedor_id not in (None, ""):
        if int(proveedor_id) == actual.get("proveedor_id"):
            elegido = _run(
                client.table("proveedores").select("*").eq("id", int(proveedor_id)).limit(1)
            )
            nombre = elegido[0]["nombre"] if elegido else actual.get("proveedor")
            cambios["proveedor_id"], cambios["proveedor"] = int(proveedor_id), nombre
        else:
            elegido = _proveedor_vigente(client, proveedor_id)
            cambios["proveedor_id"], cambios["proveedor"] = elegido["id"], elegido["nombre"]
    aviso = None
    previo = actual.get("tipo_cambio")
    if tipo_cambio is not None and not (isinstance(tipo_cambio, str) and not tipo_cambio.strip()):
        parse_tipo_cambio(tipo_cambio)  # an explicit 0 or negative is an error, not «empty»
    if tipo_cambio not in (None, "", 0) and (
        previo in (None, "") or parse_decimal(previo) != parse_tipo_cambio(tipo_cambio)
    ):
        cambios["tipo_cambio"] = str(parse_tipo_cambio(tipo_cambio))
        cambios["tipo_cambio_origen"] = ORIGEN_MANUAL
    elif actual.get("tipo_cambio_origen") != ORIGEN_MANUAL and (
        previo in (None, "") or fecha_gasto.isoformat() != str(actual.get("fecha"))
    ):
        tc, origen, aviso = cotizar(fecha_gasto)
        if tc is not None:
            cambios["tipo_cambio"] = str(tc)
            cambios["tipo_cambio_origen"] = origen
        else:
            cambios["tipo_cambio"] = None
            cambios["tipo_cambio_origen"] = None
    assert set(cambios) <= set(CAMPOS_EDITABLES_GASTO)

    filas = _run(
        client.table("gastos").update(cambios).eq("id", int(gasto_id)).eq("anulado", False)
    )
    if not filas:
        raise FinanzasError("No se pudo guardar: el gasto ya no existe o fue anulado.")
    filas[0]["rubro_id"] = item["rubro_id"]  # the database sets it from the item
    return filas[0], aviso


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
    es_imprevistos: bool = False,
) -> tuple[Fila, str | None]:
    """Insert a budget item dated today, with today's MEP (F-03 D7).

    ``monto`` may be empty or zero: items can be listed first and priced later.
    """

    fecha = hoy()
    fila: Fila = {
        "obra_id": int(obra_id),
        "fecha": fecha.isoformat(),
        "monto": str(parse_monto_item(monto)),
        "moneda": _moneda(moneda),
        "rubro_id": _rubro_activo(client, rubro_id)["id"],
        "descripcion": _texto(descripcion, "la descripción", _DESCRIPCION_MAX, False),
    }
    if es_imprevistos:
        if imprevistos_vigente(list_presupuesto(client, int(obra_id))):
            raise FinanzasError("Esta obra ya tiene un ítem de imprevistos.")
        fila["es_imprevistos"] = True
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


IMPREVISTOS = "Imprevistos"
PORCENTAJE_IMPREVISTOS = Decimal("0.10")


def imprevistos_vigente(items: Iterable[Fila]) -> Fila | None:
    return next((i for i in items if i.get("es_imprevistos") and not i.get("anulado")), None)


def _rubro_otros(client: Client) -> Fila:
    for rubro in list_rubros(client, incluir_inactivos=True):
        if normalizar(rubro["nombre"]) == "otros":
            return rubro
    raise FinanzasError("No existe el rubro «Otros».")


def crear_imprevistos(client: Client, obra: Fila) -> tuple[Fila, str | None]:
    """The «Imprevistos» item of a new obra (#35 R12).

    10 % of the obra's budget (0 without one), in the obra's currency, rubro Otros.
    Computed once: later changes to the obra's budget don't touch it.
    """

    base = obra.get("presupuesto")
    monto = Decimal(0) if base in (None, "") else parse_decimal(base) * PORCENTAJE_IMPREVISTOS
    monto = max(monto, Decimal(0)).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)
    fila = {
        "obra_id": int(obra["id"]),
        "fecha": hoy().isoformat(),
        "monto": str(monto),
        "moneda": _moneda(obra.get("moneda") or "ARS"),
        "rubro_id": _rubro_otros(client)["id"],
        "descripcion": IMPREVISTOS,
        "es_imprevistos": True,
    }
    aviso = _con_cotizacion(fila, hoy(), None) if monto > 0 else None
    filas = _run(client.table("presupuesto_items").insert(fila))
    return (filas[0] if filas else fila), aviso


def completar_cotizacion_imprevistos(client: Client, items: list[Fila]) -> list[Fila]:
    """Fill the MEP of «Imprevistos» items the database created without one.

    The migration (supabase_schema.sql) can't query the MEP; the first time the
    budget is shown, the app completes it as ``auto``. Never raises.
    """

    resultado = []
    for item in items:
        pendiente = (
            item.get("es_imprevistos")
            and not item.get("anulado")
            and item.get("tipo_cambio") in (None, "")
            and parse_decimal(item.get("monto") or 0) > 0
        )
        if pendiente:
            try:
                tc, origen, _ = cotizar(_fecha(item.get("fecha")))
                if tc is not None:
                    cambios = {"tipo_cambio": str(tc), "tipo_cambio_origen": origen}
                    # Only if it is still empty: never overwrite a manual rate saved
                    # meanwhile by someone else (R4).
                    filas = _run(
                        client.table("presupuesto_items")
                        .update(cambios)
                        .eq("id", item["id"])
                        .eq("anulado", False)
                        .is_("tipo_cambio", "null")
                    )
                    item = filas[0] if filas else get_presupuesto_item(client, item["id"])
            except FinanzasError:
                pass
        resultado.append(item)
    return resultado


def find_items(client: Client, obra_id: int, texto: str, rubro: str | None = None) -> list[Fila]:
    """Vigent budget items of the obra matching ``texto`` (for the agent).

    Exact description first, else partial; if no description matches, items
    whose rubro matches. ``rubro`` narrows the result when given.
    """

    buscado = normalizar(texto or "")
    if not buscado:
        return []
    rubros = {r["id"]: normalizar(r["nombre"]) for r in list_rubros(client, incluir_inactivos=True)}
    vigentes = [i for i in list_presupuesto(client, int(obra_id)) if not i.get("anulado")]
    if rubro and normalizar(rubro):
        filtro = normalizar(rubro)
        vigentes = [i for i in vigentes if filtro in rubros.get(i["rubro_id"], "")]

    def desc(i: Fila) -> str:
        return normalizar(i.get("descripcion") or "")

    exactos = [i for i in vigentes if desc(i) == buscado]
    if exactos:
        return exactos
    parciales = [i for i in vigentes if buscado in desc(i)]
    if parciales:
        return parciales
    return [i for i in vigentes if buscado in rubros.get(i["rubro_id"], "")]


def get_presupuesto_item(client: Client, item_id: int) -> Fila:
    filas = _run(client.table("presupuesto_items").select("*").eq("id", int(item_id)).limit(1))
    if not filas:
        raise FinanzasError("No se encontró el ítem del presupuesto.")
    return filas[0]


# Only these columns can change after creation (F-03 R9). The database enforces
# the same list with column privileges, so obra, fecha and author are fixed.
CAMPOS_EDITABLES_ITEM = (
    "rubro_id",
    "descripcion",
    "monto",
    "moneda",
    "tipo_cambio",
    "tipo_cambio_origen",
)


def update_presupuesto_item(
    client: Client,
    item_id: int,
    *,
    monto: Any,
    moneda: str,
    rubro_id: Any,
    descripcion: str | None = None,
    tipo_cambio: Any = None,
) -> Fila:
    """Edit a budget item (F-03 R9).

    ``tipo_cambio``: empty keeps the current rate; a different value replaces it
    and marks it ``manual``. A deleted (anulado) item can't be edited.
    """

    actual = get_presupuesto_item(client, item_id)
    if actual.get("anulado"):
        raise FinanzasError("Este ítem fue borrado: ya no se puede editar.")

    # Keeping a rubro that was deactivated later is allowed (R7); changing to one isn't.
    if rubro_id is not None and str(rubro_id) == str(actual.get("rubro_id")):
        rubro = int(actual["rubro_id"])
    else:
        rubro = _rubro_activo(client, rubro_id)["id"]

    cambios: Fila = {
        "rubro_id": rubro,
        "descripcion": _texto(descripcion, "la descripción", _DESCRIPCION_MAX, False),
        "monto": str(parse_monto_item(monto)),
        "moneda": _moneda(moneda),
    }
    if tipo_cambio not in (None, "", 0):
        nuevo = parse_tipo_cambio(tipo_cambio)
        previo = actual.get("tipo_cambio")
        if previo in (None, "") or parse_decimal(previo) != nuevo:
            cambios["tipo_cambio"] = str(nuevo)
            cambios["tipo_cambio_origen"] = ORIGEN_MANUAL
    assert set(cambios) <= set(CAMPOS_EDITABLES_ITEM)

    filas = _run(
        client.table("presupuesto_items")
        .update(cambios)
        .eq("id", int(item_id))
        .eq("anulado", False)
    )
    if not filas:
        raise FinanzasError("No se pudo guardar: el ítem ya no existe o fue borrado.")
    return filas[0]


def anular_presupuesto_item(client: Client, item_id: int) -> Fila:
    """«Borrar» an item and its gastos: hidden from lists and totals, kept in the
    database (R10, #35 R12b).

    The database cancels the gastos too (trigger ``presupuesto_items_propaga``);
    doing it here as well keeps both paths consistent.
    """

    filas = _run(client.table("presupuesto_items").update({"anulado": True}).eq("id", item_id))
    if not filas:
        raise FinanzasError("No se encontró el ítem del presupuesto.")
    _run(
        client.table("gastos")
        .update({"anulado": True})
        .eq("presupuesto_item_id", int(item_id))
        .eq("anulado", False)
    )
    return filas[0]


borrar_presupuesto_item = anular_presupuesto_item


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
class FilaItem:
    """One budget item with its gastos, in the summary's currency (#35)."""

    item: Fila
    presupuestado: Decimal = Decimal(0)
    gastado: Decimal = Decimal(0)
    gastos: list[Fila] = field(default_factory=list)  # all of them, cancelled too
    sin_convertir: list[Fila] = field(default_factory=list)

    @property
    def saldo(self) -> Decimal:
        return self.presupuestado - self.gastado

    @property
    def ejecutado(self) -> Decimal | None:
        return self.gastado / self.presupuestado if self.presupuestado > 0 else None

    @property
    def gastos_vigentes(self) -> list[Fila]:
        return [g for g in self.gastos if not g.get("anulado")]


@dataclass
class Resumen:
    moneda: str
    filas: list[FilaResumen] = field(default_factory=list)
    # Vigent items with their gastos, by id (#35).
    items: dict[int, FilaItem] = field(default_factory=dict)
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
    items = list(items)
    # A gasto's rubro is its item's (the database keeps them in sync, CA-35).
    rubro_de_item = {i["id"]: i["rubro_id"] for i in items if "id" in i}
    resumen.items = {i["id"]: FilaItem(i) for i in items if "id" in i and not i.get("anulado")}

    def acumular(fila: Fila, campo: str, rubro_id: int) -> Decimal | None:
        if parse_decimal(fila["monto"]) == 0:
            valor = Decimal(0)  # zero needs no rate in any currency
        else:
            valor = convertir(fila["monto"], fila["moneda"], fila.get("tipo_cambio"), moneda)
        if valor is None:
            resumen.sin_convertir.append(fila)
            return None
        nombre = info.get(rubro_id, {}).get("nombre", f"Rubro #{rubro_id}")
        destino = filas.setdefault(rubro_id, FilaResumen(rubro_id, nombre))
        setattr(destino, campo, getattr(destino, campo) + valor)
        return valor

    for item in items:
        if item.get("anulado"):
            continue
        valor = acumular(item, "presupuestado", item["rubro_id"])
        del_item = resumen.items.get(item.get("id"))
        if del_item is None:
            continue
        if valor is None:
            del_item.sin_convertir.append(item)
        else:
            del_item.presupuestado = valor
    for gasto in gastos:
        del_item = resumen.items.get(gasto.get("presupuesto_item_id"))
        if del_item is not None:
            del_item.gastos.append(gasto)
        if gasto.get("anulado"):
            continue
        rubro_id = rubro_de_item.get(gasto.get("presupuesto_item_id"), gasto["rubro_id"])
        valor = acumular(gasto, "gastado", rubro_id)
        if del_item is None:
            continue
        if valor is None:
            del_item.sin_convertir.append(gasto)
        else:
            del_item.gastado += valor

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


DENTRO = "Dentro del presupuesto"
CERCA = "Cerca del límite"
EXCEDIDO = "Excedido"
SIN_PRESUPUESTO = "Sin presupuesto asignado"
ICONOS = {DENTRO: "🟢", CERCA: "🟡", EXCEDIDO: "🔴", SIN_PRESUPUESTO: "⚪"}
_LIMITE_CERCA = Decimal("0.9")


def estado(gastado: Decimal, presupuestado: Decimal) -> str:
    """Traffic light in words (#35 R16): green < 90 %, yellow 90-100 %, red > 100 %.

    Without budget: «Excedido» if something was spent, else «Sin presupuesto asignado».
    """

    if presupuestado <= 0:
        return EXCEDIDO if gastado > 0 else SIN_PRESUPUESTO
    proporcion = gastado / presupuestado
    if proporcion > 1:
        return EXCEDIDO
    if proporcion >= _LIMITE_CERCA:
        return CERCA
    return DENTRO


def estado_con_icono(gastado: Decimal, presupuestado: Decimal) -> str:
    """Icon plus words, so meaning never depends on color alone."""

    texto = estado(gastado, presupuestado)
    return f"{ICONOS[texto]} {texto}"


def estado_desvio(desvio: Decimal, presupuestado: Decimal) -> str:
    """Status from the desvío (gastado − presupuestado); same scale as ``estado``."""

    return estado(desvio + presupuestado, presupuestado)


def describe_resumen(res: Resumen, nombre_obra: str) -> str:
    """Prompt-ready summary for the agent."""

    m = res.moneda
    estado_total = estado_desvio(res.desvio, res.presupuestado)
    lineas = [
        f"Presupuesto y gastos de {nombre_obra} en {m}:",
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
    if res.items:
        lineas.append("Por ítem del presupuesto:")
        for fi in res.items.values():
            nombre = fi.item.get("descripcion") or "Sin descripción"
            lineas.append(
                f"- {nombre}: total {formato_monto(fi.presupuestado, m)}, gastado "
                f"{formato_monto(fi.gastado, m)} ({formato_porcentaje(fi.ejecutado)}), saldo "
                f"{formato_monto(fi.saldo, m)}, {len(fi.gastos_vigentes)} gasto(s) "
                f"({estado(fi.gastado, fi.presupuestado)})"
            )
    if res.incompleto:
        lineas.append(
            f"ATENCIÓN: {len(res.sin_convertir)} registro(s) sin cotización no se pudieron "
            f"convertir a {m}; el total está incompleto."
        )
    return "\n".join(lineas)
