"""Writes the agent proposes and the user confirms with a button (#51).

The agent never saves anything by itself: its write tools check the request
and leave a *propuesta* (what would be saved, in words). The screen shows it
with «Confirmar» and «Cancelar», and only a click runs ``ejecutar``. So neither
an ambiguous message nor an instruction hidden in stored data can make the agent
write: a person always decides, looking at exactly what will be saved.

Propuestas are plain dicts (they live in the chat history of the session):
``{"tipo", "resumen", "datos", "estado", "resultado"}``. No Streamlit here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from atrium import finanzas, obras, proveedores

if TYPE_CHECKING:
    from supabase import Client

NOTA, OBRA, GASTO, PROVEEDOR = "nota", "obra", "gasto", "proveedor"
PENDIENTE, CONFIRMADA, CANCELADA, FALLIDA = "pendiente", "confirmada", "cancelada", "fallida"

Propuesta = dict[str, Any]


def nueva(tipo: str, resumen: str, datos: dict[str, Any]) -> Propuesta:
    return {
        "tipo": tipo,
        "resumen": resumen,
        "datos": datos,
        "estado": PENDIENTE,
        "resultado": None,
    }


def ejecutar(client: Client, autor: str | None, propuesta: Propuesta) -> str:
    """Save a confirmed propuesta. Returns what was done, in words.

    Everything is validated again here (the data may have changed since the
    agent proposed it). Raises the domain's error with a message ready to show.
    """

    if propuesta.get("estado") != PENDIENTE:
        raise ValueError("Esta propuesta ya no está pendiente.")
    tipo, datos = propuesta["tipo"], propuesta["datos"]
    if tipo == NOTA:
        obras.add_nota(client, datos["obra_id"], datos["nota"], autor=autor, fecha=datos["fecha"])
        return f"📝 Nota agregada a la bitácora de «{datos['obra']}»"
    if tipo == OBRA:
        obras.update_obra(client, datos["obra_id"], dict(datos["cambios"]))
        detalle = ", ".join(
            f"{k} → {v}{'%' if k == 'avance' else ''}" for k, v in datos["cambios"].items()
        )
        return f"✏️ «{datos['obra']}» actualizada: {detalle}"
    if tipo == GASTO:
        gasto, aviso = finanzas.add_gasto(
            client,
            datos["item_id"],
            monto=datos["monto"],
            moneda=datos["moneda"],
            descripcion=datos["descripcion"],
            fecha=datos["fecha"],
            proveedor_id=datos.get("proveedor_id"),
        )
        texto = (
            f"💸 Gasto registrado en «{datos['obra']}»: "
            f"{finanzas.formato_monto(gasto['monto'], gasto['moneda'])} · {datos['item']}"
        )
        return f"{texto} ({aviso})" if aviso else texto
    if tipo == PROVEEDOR:
        nuevo = proveedores.create_proveedor(client, dict(datos["datos"]))
        return f"🏢 Proveedor agregado: «{nuevo['nombre']}»"
    raise ValueError(f"Tipo de propuesta desconocido: {tipo}")


ERRORES = (obras.ObrasError, finanzas.FinanzasError, proveedores.ProveedoresError, ValueError)
