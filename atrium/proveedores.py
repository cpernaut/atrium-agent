"""F-06 · Proveedores (#37): the team's shared list, ratings and purchases.

Uses the signed-in user's Supabase client, so row-level security applies (see
``supabase_schema.sql``). No Streamlit dependency; callers decide how to show a
``ProveedoresError`` (messages are in Spanish, ready to display).

- «Eliminar» archives (``archivado``): the row and its gastos stay.
- Names are unique ignoring case, accents and extra spaces, like rubros.
- Each team member has one rating (1 to 5 stars) per proveedor and can change it.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from atrium.finanzas import formato_monto, normalizar

if TYPE_CHECKING:
    from supabase import Client

Fila = dict[str, Any]

NOMBRE_MIN, NOMBRE_MAX = 2, 120
_TEXTO_MAX = {"contacto": 120, "zona": 120, "notas": 1000}
_COMENTARIO_MAX = 500
_PAGINA = 1000
_MAX_PAGINAS = 200

# Columns the team can edit; supabase_schema.sql grants the same list.
CAMPOS_EDITABLES_PROVEEDOR = (
    "nombre",
    "contacto",
    "telefono",
    "email",
    "web",
    "cuit",
    "zona",
    "notas",
    "rubro_ids",
)


class ProveedoresError(RuntimeError):
    """Reading or writing proveedores failed, or the input is invalid."""


def _run(query) -> list[Fila]:
    try:
        return query.execute().data or []
    except Exception as exc:  # noqa: BLE001 - wrap the provider error
        mensaje = str(exc)
        if "proveedores_nombre_clave_unico" in mensaje:
            raise ProveedoresError("Ya existe un proveedor con ese nombre.") from exc
        if "una_por_socio" in mensaje:
            raise ProveedoresError(
                "Ya calificaste a este proveedor: editá tu calificación."
            ) from exc
        raise ProveedoresError(mensaje) from exc


def _run_all(build) -> list[Fila]:
    """Every row of a query, page by page (Supabase caps each response)."""

    filas: list[Fila] = []
    for pagina in range(_MAX_PAGINAS):
        lote = _run(build().range(pagina * _PAGINA, (pagina + 1) * _PAGINA - 1))
        filas += lote
        if len(lote) < _PAGINA:
            return filas
    raise ProveedoresError("Demasiados registros para leer de una vez.")


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
# Strict: letters, digits and . _ + - only. No «?», «&», «#» or «%»: the Mail
# button builds a mailto: link, and those would let a stored address add hidden
# recipients («x@y.com?bcc=…»).
_EMAIL = re.compile(r"^[A-Za-z0-9._+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_TELEFONO = re.compile(r"^[0-9+() -]{6,30}$")
_WEB = re.compile(r"^https://\S+$")


def _texto(valor: Any, que: str, maximo: int) -> str | None:
    texto = " ".join(str(valor or "").split())
    if not texto:
        return None
    if len(texto) > maximo:
        raise ProveedoresError(f"{que.capitalize()} puede tener hasta {maximo} caracteres.")
    return texto


def _nombre(valor: Any) -> str:
    nombre = " ".join(str(valor or "").split())
    if len(nombre) < NOMBRE_MIN:
        raise ProveedoresError("El proveedor necesita un nombre (al menos 2 letras).")
    if len(nombre) > NOMBRE_MAX:
        raise ProveedoresError(f"El nombre puede tener hasta {NOMBRE_MAX} caracteres.")
    return nombre


def normalizar_cuit(valor: Any) -> str | None:
    """«20123456786» or «20-12345678-6» -> «20-12345678-6», checking the last digit."""

    digitos = re.sub(r"[\s-]", "", str(valor or ""))
    if not digitos:
        return None
    if not re.fullmatch(r"\d{11}", digitos):
        raise ProveedoresError("El CUIT tiene que tener 11 números (por ejemplo 30-71234567-1).")
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    resto = sum(int(d) * p for d, p in zip(digitos[:10], pesos, strict=True)) % 11
    verificador = {0: 0, 1: 9}.get(resto, 11 - resto)
    if int(digitos[10]) != verificador:
        raise ProveedoresError("El CUIT no es válido: revisá los números.")
    return f"{digitos[:2]}-{digitos[2:10]}-{digitos[10]}"


def _telefono(valor: Any) -> str | None:
    texto = " ".join(str(valor or "").split())
    if not texto:
        return None
    if not _TELEFONO.fullmatch(texto) or len(re.sub(r"\D", "", texto)) < 6:
        raise ProveedoresError("El teléfono solo puede tener números, espacios, +, - y paréntesis.")
    return texto


def _email(valor: Any) -> str | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    if len(texto) > 120 or not _EMAIL.fullmatch(texto):
        raise ProveedoresError("El mail no es válido (por ejemplo ventas@proveedor.com).")
    return texto


def _web(valor: Any) -> str | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    tiene_esquema = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", texto)
    if not tiene_esquema:
        texto = "https://" + texto  # «hierros.com.ar» -> «https://hierros.com.ar»
    if len(texto) > 300 or not _WEB.fullmatch(texto):
        raise ProveedoresError(
            "La web tiene que empezar con https:// (por ejemplo https://proveedor.com)."
        )
    return texto


def _rubro_ids(valor: Any) -> list[int]:
    try:
        ids = sorted({int(v) for v in (valor or [])})
    except (TypeError, ValueError) as exc:
        raise ProveedoresError("Los rubros elegidos no son válidos.") from exc
    return ids


def _datos(datos: dict[str, Any]) -> Fila:
    """Validated columns for an insert or update (only the keys given)."""

    otros = sorted(set(datos) - set(CAMPOS_EDITABLES_PROVEEDOR))
    if otros:
        raise ProveedoresError(f"Esos datos del proveedor no se pueden editar: {', '.join(otros)}.")
    limpio: Fila = {}
    for campo, valor in datos.items():
        if campo == "nombre":
            limpio[campo] = _nombre(valor)
        elif campo == "telefono":
            limpio[campo] = _telefono(valor)
        elif campo == "email":
            limpio[campo] = _email(valor)
        elif campo == "web":
            limpio[campo] = _web(valor)
        elif campo == "cuit":
            limpio[campo] = normalizar_cuit(valor)
        elif campo == "rubro_ids":
            limpio[campo] = _rubro_ids(valor)
        else:
            limpio[campo] = _texto(valor, campo, _TEXTO_MAX[campo])
    return limpio


# --------------------------------------------------------------------------- #
# Proveedores
# --------------------------------------------------------------------------- #
def list_proveedores(client: Client, incluir_archivados: bool = False) -> list[Fila]:
    """The shared list, by name (archived ones only if asked)."""

    def build():
        query = client.table("proveedores").select("*").order("nombre").order("id")
        return query if incluir_archivados else query.eq("archivado", False)

    return _run_all(build)


def get_proveedor(client: Client, proveedor_id: Any) -> Fila:
    try:
        proveedor_id = int(proveedor_id)
    except (TypeError, ValueError) as exc:
        raise ProveedoresError("Elegí un proveedor.") from exc
    filas = _run(client.table("proveedores").select("*").eq("id", proveedor_id).limit(1))
    if not filas:
        raise ProveedoresError("No se encontró el proveedor.")
    return filas[0]


def filtrar(
    proveedores: list[Fila],
    texto: str = "",
    rubro_id: int | None = None,
    rubros: dict[int, str] | None = None,
) -> list[Fila]:
    """Proveedores whose name, contact, phone, mail or rubros match ``texto``."""

    buscado = normalizar(texto or "")
    resultado = []
    for p in proveedores:
        if rubro_id is not None and rubro_id not in (p.get("rubro_ids") or []):
            continue
        if buscado:
            campos = [p.get(c) or "" for c in ("nombre", "contacto", "telefono", "email", "zona")]
            campos += [(rubros or {}).get(r, "") for r in p.get("rubro_ids") or []]
            if not any(buscado in normalizar(str(c)) for c in campos):
                continue
        resultado.append(p)
    return resultado


def find_proveedores(client: Client, texto: str) -> list[Fila]:
    """Active proveedores matching ``texto``: exact name first, else partial match."""

    buscado = normalizar(texto or "")
    if not buscado:
        return []
    lista = list_proveedores(client)
    exactos = [p for p in lista if normalizar(p["nombre"]) == buscado]
    return exactos or [p for p in lista if buscado in normalizar(p["nombre"])]


def _duplicado(client: Client, nombre: str, excepto: int | None = None) -> None:
    for p in list_proveedores(client, incluir_archivados=True):
        if p["id"] != excepto and normalizar(p["nombre"]) == normalizar(nombre):
            if p.get("archivado"):
                raise ProveedoresError(
                    f"Ya existe el proveedor «{p['nombre']}», eliminado: restauralo desde "
                    "«Mostrar eliminados»."
                )
            raise ProveedoresError(f"Ya existe el proveedor «{p['nombre']}».")


def create_proveedor(client: Client, datos: dict[str, Any]) -> Fila:
    if "nombre" not in datos:
        raise ProveedoresError("El proveedor necesita un nombre (al menos 2 letras).")
    fila = _datos(datos)
    _duplicado(client, fila["nombre"])
    filas = _run(client.table("proveedores").insert(fila))
    return filas[0] if filas else fila


def update_proveedor(client: Client, proveedor_id: int, datos: dict[str, Any]) -> Fila:
    if not datos:
        raise ProveedoresError("No hay cambios para guardar.")
    cambios = _datos(datos)
    if "nombre" in cambios:
        _duplicado(client, cambios["nombre"], excepto=int(proveedor_id))
    filas = _run(client.table("proveedores").update(cambios).eq("id", int(proveedor_id)))
    if not filas:
        raise ProveedoresError("No se encontró el proveedor.")
    return filas[0]


def set_archivado(client: Client, proveedor_id: int, archivado: bool) -> Fila:
    """«Eliminar» (archive) or restore a proveedor. Its gastos keep pointing at it."""

    filas = _run(
        client.table("proveedores")
        .update({"archivado": bool(archivado)})
        .eq("id", int(proveedor_id))
    )
    if not filas:
        raise ProveedoresError("No se encontró el proveedor.")
    return filas[0]


# --------------------------------------------------------------------------- #
# Contact links (validated data only: never user text inside a URL as-is)
# --------------------------------------------------------------------------- #
def _digitos_internacionales(telefono: str) -> str | None:
    """Argentine number in international digits («221 555-1234» -> «542215551234»)."""

    digitos = re.sub(r"\D", "", telefono or "")
    if len(digitos) < 6:
        return None
    if telefono.strip().startswith("+") or digitos.startswith("54"):
        return digitos
    return "54" + digitos.lstrip("0")


def enlaces_contacto(proveedor: Fila) -> list[tuple[str, str]]:
    """(label, url) buttons for the ficha: call, WhatsApp, mail, web."""

    enlaces = []
    internacional = _digitos_internacionales(proveedor.get("telefono") or "")
    if internacional:
        enlaces.append(("📞 Llamar", f"tel:+{internacional}"))
        # WhatsApp numbers in Argentina are mobiles: 54 9 + area code + number.
        movil = internacional
        if movil.startswith("54") and not movil.startswith("549"):
            movil = "549" + movil[2:]
        enlaces.append(("💬 WhatsApp", f"https://wa.me/{movil}"))
    email = proveedor.get("email")
    if email and _EMAIL.fullmatch(email):
        enlaces.append(("✉️ Mail", f"mailto:{email}"))
    web = proveedor.get("web")
    if web and _WEB.fullmatch(web):
        enlaces.append(("🌐 Web", web))
    return enlaces


# --------------------------------------------------------------------------- #
# Ratings
# --------------------------------------------------------------------------- #
def list_calificaciones(client: Client, proveedor_id: int | None = None) -> list[Fila]:
    """Ratings (of one proveedor, or all), newest first."""

    def build():
        query = (
            client.table("proveedor_calificaciones")
            .select("*")
            .order("created_at", desc=True)
            .order("id", desc=True)
        )
        return query.eq("proveedor_id", int(proveedor_id)) if proveedor_id is not None else query

    return _run_all(build)


def calificar(
    client: Client,
    proveedor_id: int,
    user_id: str,
    estrellas: Any,
    comentario: str | None = None,
    autor: str | None = None,
) -> Fila:
    """Save this user's rating (1 to 5) of the proveedor, replacing their previous one."""

    try:
        estrellas = int(estrellas)
    except (TypeError, ValueError) as exc:
        raise ProveedoresError("Elegí de 1 a 5 estrellas.") from exc
    if not 1 <= estrellas <= 5:
        raise ProveedoresError("Elegí de 1 a 5 estrellas.")
    comentario = _texto(comentario, "el comentario", _COMENTARIO_MAX)
    proveedor = get_proveedor(client, proveedor_id)
    mia = _run(
        client.table("proveedor_calificaciones")
        .select("*")
        .eq("proveedor_id", proveedor["id"])
        .eq("creado_por", user_id)
        .limit(1)
    )
    datos = {"estrellas": estrellas, "comentario": comentario}
    if mia:
        filas = _run(
            client.table("proveedor_calificaciones")
            .update(datos)
            .eq("id", mia[0]["id"])
            .eq("creado_por", user_id)
        )
        if not filas:
            raise ProveedoresError("No se pudo guardar tu calificación.")
        return filas[0]
    if proveedor.get("archivado"):
        raise ProveedoresError("Este proveedor fue eliminado: restauralo para calificarlo.")
    # The database signs it with the login's email; ``autor`` only helps the fake.
    fila = {"proveedor_id": proveedor["id"], "creado_por": user_id, "autor": autor, **datos}
    filas = _run(client.table("proveedor_calificaciones").insert(fila))
    return filas[0] if filas else fila


def promedio(calificaciones: list[Fila]) -> tuple[Decimal | None, int]:
    """(average with one decimal, count). The average is None without ratings."""

    if not calificaciones:
        return None, 0
    total = sum(Decimal(int(c["estrellas"])) for c in calificaciones)
    return (total / len(calificaciones)).quantize(Decimal("0.1")), len(calificaciones)


def promedios(calificaciones: list[Fila]) -> dict[int, tuple[Decimal | None, int]]:
    """{proveedor_id: (average, count)} for the list screen."""

    por_proveedor: dict[int, list[Fila]] = defaultdict(list)
    for c in calificaciones:
        por_proveedor[c["proveedor_id"]].append(c)
    return {pid: promedio(filas) for pid, filas in por_proveedor.items()}


def estrellas_txt(valor: Decimal | float | int | None, cantidad: int | None = None) -> str:
    """«★★★★☆ 4,3 · 3 calificaciones»: always the number too, never only the drawing."""

    if valor is None:
        return "Sin calificaciones"
    llenas = int(Decimal(str(valor)))  # whole stars only: 4,5 shows four (and the number)
    numero = f"{Decimal(str(valor)):.1f}".replace(".", ",")
    texto = f"{'★' * llenas}{'☆' * (5 - llenas)} {numero}"
    if cantidad is not None:
        texto += f" · {cantidad} calificaci{'ón' if cantidad == 1 else 'ones'}"
    return texto


# --------------------------------------------------------------------------- #
# Purchases (gastos of the proveedor, in every obra)
# --------------------------------------------------------------------------- #
@dataclass
class ComprasObra:
    obra_id: int
    obra: str
    gastos: list[Fila] = field(default_factory=list)
    totales: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class Compras:
    obras: list[ComprasObra]
    totales: dict[str, Decimal]
    cantidad: int

    def total_txt(self) -> str:
        """Totals per currency, never added across currencies (F-03)."""

        if not self.totales:
            return "Sin compras todavía"
        return " · ".join(formato_monto(v, m) for m, v in sorted(self.totales.items()))


def _gastos_con_proveedor(client: Client, proveedor_id: int | None = None) -> list[Fila]:
    def build():
        query = client.table("gastos").select("*").eq("anulado", False).order("fecha", desc=True)
        return query.eq("proveedor_id", int(proveedor_id)) if proveedor_id is not None else query

    return [g for g in _run_all(build) if g.get("proveedor_id") is not None]


def _sumar(totales: dict[str, Decimal], gasto: Fila) -> None:
    moneda = gasto.get("moneda") or "ARS"
    totales[moneda] = totales.get(moneda, Decimal(0)) + Decimal(str(gasto["monto"]))


def compras(client: Client, proveedor_id: int) -> Compras:
    """What the team bought from this proveedor: per obra and per currency."""

    gastos = _gastos_con_proveedor(client, proveedor_id)
    nombres = {o["id"]: o["nombre"] for o in _run(client.table("obras").select("id, nombre"))}
    por_obra: dict[int, ComprasObra] = {}
    totales: dict[str, Decimal] = {}
    for g in gastos:
        obra = por_obra.setdefault(
            g["obra_id"],
            ComprasObra(g["obra_id"], nombres.get(g["obra_id"], f"Obra #{g['obra_id']}")),
        )
        obra.gastos.append(g)
        _sumar(obra.totales, g)
        _sumar(totales, g)
    obras = sorted(por_obra.values(), key=lambda o: normalizar(o.obra))
    return Compras(obras=obras, totales=totales, cantidad=len(gastos))


def resumen_compras(client: Client) -> dict[int, Compras]:
    """{proveedor_id: Compras} without per-obra detail, for the list screen."""

    resumen: dict[int, dict] = {}
    for g in _gastos_con_proveedor(client):
        datos = resumen.setdefault(g["proveedor_id"], {"obras": set(), "totales": {}, "n": 0})
        datos["obras"].add(g["obra_id"])
        datos["n"] += 1
        _sumar(datos["totales"], g)
    return {
        pid: Compras(
            obras=[ComprasObra(o, "") for o in sorted(d["obras"])],
            totales=d["totales"],
            cantidad=d["n"],
        )
        for pid, d in resumen.items()
    }


# --------------------------------------------------------------------------- #
# Text for the agent
# --------------------------------------------------------------------------- #
def describe_proveedor(
    proveedor: Fila,
    rubros: dict[int, str],
    calificaciones: list[Fila],
    compras_: Compras | None = None,
) -> str:
    """A compact, prompt-ready summary of one proveedor."""

    prom, n = promedio(calificaciones)
    lineas = [f"Proveedor: {proveedor['nombre']} (#{proveedor['id']})"]
    if proveedor.get("archivado"):
        lineas.append("Estado: eliminado (archivado)")
    nombres_rubros = [rubros[r] for r in proveedor.get("rubro_ids") or [] if r in rubros]
    if nombres_rubros:
        lineas.append(f"Rubros: {', '.join(nombres_rubros)}")
    for etiqueta, campo in (
        ("Contacto", "contacto"),
        ("Teléfono", "telefono"),
        ("Mail", "email"),
        ("Web", "web"),
        ("CUIT", "cuit"),
        ("Zona", "zona"),
        ("Notas", "notas"),
    ):
        if proveedor.get(campo):
            lineas.append(f"{etiqueta}: {proveedor[campo]}")
    lineas.append(f"Calificación: {estrellas_txt(prom, n)}")
    for c in calificaciones[:5]:
        comentario = f" «{c['comentario']}»" if c.get("comentario") else ""
        lineas.append(f"- {c['estrellas']}/5 de {c.get('autor') or 'un socio'}{comentario}")
    if compras_ is not None:
        lineas.append(f"Compras: {compras_.cantidad} gastos · {compras_.total_txt()}")
        for o in compras_.obras:
            totales = " · ".join(formato_monto(v, m) for m, v in sorted(o.totales.items()))
            lineas.append(f"- {o.obra}: {len(o.gastos)} gastos · {totales}")
    return "\n".join(lineas)
