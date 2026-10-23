"""Obras tracker: data access for the ``obras`` and ``bitacora`` tables.

Uses the signed-in user's Supabase client, so row-level security applies (see
``supabase_schema.sql``). No Streamlit dependency; callers decide how to show
an ``ObrasError``.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from atrium import sanidad

if TYPE_CHECKING:
    from supabase import Client

ESTADOS = ("Planificación", "En curso", "Pausada", "Terminada", "Cancelada")
TIPOS = ("Vivienda", "Reforma", "Ampliación", "Regularización", "Local comercial", "Otro")
MONEDAS = ("ARS", "USD")

# Municipio -> PDF in docs/ with its building code. Municipios not listed here
# have no normativa loaded yet.
NORMATIVA_POR_MUNICIPIO = {
    "La Plata": "Codigo Edificacion de La Plata.pdf",
    "Berazategui": "codigo-edificacion-berazategui.pdf",
}
MUNICIPIOS = (*NORMATIVA_POR_MUNICIPIO, "Quilmes", "Otro")

Obra = dict[str, Any]


class ObrasError(RuntimeError):
    """Reading or writing the obras tables failed, or the input is invalid."""


def _run(query) -> list[dict]:
    try:
        return query.execute().data or []
    except Exception as exc:  # noqa: BLE001 - wrap the provider error
        raise ObrasError(str(exc)) from exc


# --------------------------------------------------------------------------- #
# Obras
# --------------------------------------------------------------------------- #
def list_obras(client: Client, estado: str | None = None) -> list[Obra]:
    """All obras, newest first; optionally only those in ``estado``."""

    query = client.table("obras").select("*").order("created_at", desc=True)
    if estado:
        query = query.eq("estado", estado)
    return _run(query)


# Order in the obra picker: what is being worked on first (UX-02).
_PRIORIDAD_ESTADO = {
    estado: i
    for i, estado in enumerate(("En curso", "Planificación", "Pausada", "Terminada", "Cancelada"))
}


def ordenar_para_elegir(lista: list[Obra]) -> list[Obra]:
    """Obras for the picker: En curso first, Terminada/Cancelada last.

    The sort is stable, so within each estado the order of ``lista`` (newest
    first, as ``list_obras`` returns it) is kept.
    """

    return sorted(lista, key=lambda o: _PRIORIDAD_ESTADO.get(o.get("estado"), 99))


def obra_por_defecto(lista: list[Obra], ultima: int | None = None) -> int | None:
    """The obra to show when nothing was chosen (UX-02).

    The last one used if it still exists; else the newest En curso; else the
    first one in picker order, so a Terminada or Cancelada obra is never the
    default while another one is active.
    """

    if not lista:
        return None
    ids = {o["id"] for o in lista}
    if ultima in ids:
        return ultima
    return ordenar_para_elegir(lista)[0]["id"]


# --------------------------------------------------------------------------- #
# Obra activa: remembered per user across sessions and devices (#49 D9)
# --------------------------------------------------------------------------- #
CLAVE_OBRA_ACTIVA = "obra_activa"  # key in the user's metadata (Supabase Auth)


def obra_activa_guardada(user: Any) -> int | None:
    """The obra this user worked on last, as saved in their metadata.

    The metadata is editable by the user, so the value is treated as untrusted:
    anything that is not a positive id is ignored (and ``obra_por_defecto``
    only uses it if that obra exists).
    """

    metadata = getattr(user, "user_metadata", None) or {}
    valor = metadata.get(CLAVE_OBRA_ACTIVA) if isinstance(metadata, dict) else None
    if isinstance(valor, bool):
        return None
    try:
        valor = int(valor)
    except (TypeError, ValueError):
        return None
    return valor if valor > 0 else None


def guardar_obra_activa(client: Client, user: Any, obra_id: int) -> None:
    """Remember ``obra_id`` as this user's obra activa (their own metadata only)."""

    try:
        client.auth.update_user({"data": {CLAVE_OBRA_ACTIVA: int(obra_id)}})
    except Exception as exc:  # noqa: BLE001 - wrap the provider error
        raise ObrasError(f"No se pudo recordar la obra activa: {exc}") from exc
    metadata = getattr(user, "user_metadata", None)
    if isinstance(metadata, dict):
        metadata[CLAVE_OBRA_ACTIVA] = int(obra_id)


def get_obra(client: Client, obra_id: int) -> Obra | None:
    rows = _run(client.table("obras").select("*").eq("id", obra_id).limit(1))
    return rows[0] if rows else None


def find_obras(client: Client, texto: str) -> list[Obra]:
    """Resolve a user reference: an id (``"12"``, ``"#12"``) or part of the name."""

    texto = texto.strip().lstrip("#")
    if texto.isdigit():
        obra = get_obra(client, int(texto))
        return [obra] if obra else []
    return _run(client.table("obras").select("*").ilike("nombre", f"%{texto}%").limit(10))


# Free text of an obra: checked before saving (#53).
_TEXTOS_OBRA = {
    "nombre": "el nombre",
    "cliente": "el cliente",
    "direccion": "la dirección",
    "responsable": "el responsable",
}


def _revisar_textos(datos: dict[str, Any]) -> None:
    for campo, que in _TEXTOS_OBRA.items():
        if campo in datos and datos[campo] is not None:
            datos[campo] = sanidad.revisar(datos[campo], que, ObrasError)
            if datos[campo] and len(datos[campo]) > 200:
                raise ObrasError(f"{que.capitalize()} puede tener hasta 200 caracteres.")


def create_obra(client: Client, datos: dict[str, Any]) -> Obra:
    _revisar_textos(datos)
    if not str(datos.get("nombre") or "").strip():
        raise ObrasError("La obra necesita un nombre.")
    _validate(datos)
    rows = _run(client.table("obras").insert(datos))
    return rows[0] if rows else datos


# Columns the team can edit (#49 D4). The author and creation date never change;
# supabase_schema.sql enforces the same list with column grants.
CAMPOS_EDITABLES_OBRA = (
    "nombre",
    "cliente",
    "direccion",
    "municipio",
    "tipo",
    "estado",
    "avance",
    "responsable",
    "fecha_inicio",
    "fecha_fin_estimada",
    "presupuesto",
    "moneda",
)


def update_obra(client: Client, obra_id: int, cambios: dict[str, Any]) -> Obra:
    validar_cambios(cambios)
    rows = _run(client.table("obras").update(cambios).eq("id", obra_id))
    if not rows:
        raise ObrasError(f"No se encontró la obra #{obra_id}.")
    return rows[0]


def validar_cambios(cambios: dict[str, Any]) -> dict[str, Any]:
    """Check (and normalize in place) the changes to an obra, without saving them."""

    if not cambios:
        raise ObrasError("No hay cambios para guardar.")
    otros = sorted(set(cambios) - set(CAMPOS_EDITABLES_OBRA))
    if otros:
        raise ObrasError(f"Esos datos de la obra no se pueden editar: {', '.join(otros)}.")
    _revisar_textos(cambios)
    if "nombre" in cambios:
        cambios["nombre"] = str(cambios["nombre"] or "").strip()
        if not cambios["nombre"]:
            raise ObrasError("La obra necesita un nombre.")
    _validate(cambios)
    return cambios


def _validate(datos: dict[str, Any]) -> None:
    if "estado" in datos and datos["estado"] not in ESTADOS:
        raise ObrasError(f"Estado inválido: {datos['estado']}. Opciones: {', '.join(ESTADOS)}.")
    if "moneda" in datos and datos["moneda"] not in MONEDAS:
        raise ObrasError(f"Moneda inválida: {datos['moneda']}.")
    if datos.get("presupuesto") is not None:
        try:
            presupuesto = float(datos["presupuesto"])
        except (TypeError, ValueError) as exc:
            raise ObrasError("El presupuesto tiene que ser un número.") from exc
        if presupuesto < 0:
            raise ObrasError("El presupuesto no puede ser negativo.")
    if "avance" in datos:
        try:
            avance = int(datos["avance"])
        except (TypeError, ValueError) as exc:
            raise ObrasError("El avance tiene que ser un número entre 0 y 100.") from exc
        if not 0 <= avance <= 100:
            raise ObrasError("El avance tiene que estar entre 0 y 100.")
        datos["avance"] = avance


# --------------------------------------------------------------------------- #
# Bitácora
# --------------------------------------------------------------------------- #
def list_bitacora(client: Client, obra_id: int, limit: int | None = None) -> list[dict]:
    query = (
        client.table("bitacora")
        .select("*")
        .eq("obra_id", obra_id)
        .order("fecha", desc=True)
        .order("created_at", desc=True)
    )
    if limit:
        query = query.limit(limit)
    return _run(query)


def validar_nota(nota: str) -> str:
    """The note as it would be saved, or ObrasError saying what's wrong."""

    limpia = sanidad.revisar(nota, "la nota", ObrasError, multilinea=True)
    if not limpia:
        raise ObrasError("La nota está vacía.")
    if len(limpia) > 5000:
        raise ObrasError("La nota puede tener hasta 5000 caracteres.")
    return limpia


def add_nota(
    client: Client,
    obra_id: int,
    nota: str,
    autor: str | None = None,
    fecha: date | str | None = None,
) -> dict:
    fila: dict[str, Any] = {"obra_id": obra_id, "nota": validar_nota(nota), "autor": autor}
    if fecha:
        fila["fecha"] = fecha.isoformat() if isinstance(fecha, date) else str(fecha)
    rows = _run(client.table("bitacora").insert(fila))
    return rows[0] if rows else fila


# --------------------------------------------------------------------------- #
# Text for the agent
# --------------------------------------------------------------------------- #
def normativa_source(obra: Obra | None) -> str | None:
    """The docs/ PDF that holds the building code for this obra's municipio."""

    if not obra:
        return None
    return NORMATIVA_POR_MUNICIPIO.get(obra.get("municipio") or "")


def describe_obra(obra: Obra) -> str:
    """A compact, prompt-ready summary of one obra."""

    campos = [
        ("Obra", f"{obra.get('nombre')} (#{obra.get('id')})"),
        ("Cliente", obra.get("cliente")),
        ("Dirección", obra.get("direccion")),
        ("Municipio", obra.get("municipio")),
        ("Tipo", obra.get("tipo")),
        ("Estado", obra.get("estado")),
        ("Avance", f"{obra.get('avance', 0)}%"),
        ("Responsable", obra.get("responsable")),
        ("Inicio", obra.get("fecha_inicio")),
        ("Fin estimado", obra.get("fecha_fin_estimada")),
    ]
    if obra.get("presupuesto") is not None:
        campos.append(("Presupuesto", f"{obra['presupuesto']} {obra.get('moneda', '')}".strip()))
    return "\n".join(f"- {etiqueta}: {valor}" for etiqueta, valor in campos if valor)


def describe_obras(obras: list[Obra]) -> str:
    """One line per obra, for listings."""

    if not obras:
        return "No hay obras cargadas."
    return "\n".join(
        f"- #{o['id']} {o['nombre']} · {o.get('estado')} · {o.get('avance', 0)}%"
        + (f" · {o['municipio']}" if o.get("municipio") else "")
        + (f" · cliente {o['cliente']}" if o.get("cliente") else "")
        for o in obras
    )
