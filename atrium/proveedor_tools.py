"""Agent tools for the shared proveedores list (F-06, #37).

Registered by ``obra_tools.build_obra_tools``. Same rules as the obra tools:
they close over the signed-in user's client (RLS applies), never raise (errors
come back as text) and the one that writes records what it did in ``acciones``.
The agent never rates a proveedor and never creates one unless asked (#37 D6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, StructuredTool

from atrium import finanzas, proveedores
from atrium.guardia import PROVEEDOR, Turno

if TYPE_CHECKING:
    from supabase import Client


def resolver_proveedor(client: Client, texto: str) -> tuple[dict | None, str | None]:
    """(proveedor, None) on a unique match in the list, else (None, message for the model)."""

    matches = proveedores.find_proveedores(client, texto)
    if not matches:
        return None, (
            f"No encontré el proveedor «{texto}» en la lista de proveedores. No guardé nada: "
            "preguntale al usuario si es otro proveedor o si lo querés dar de alta "
            "(con crear_proveedor, solo si te lo confirma)."
        )
    if len(matches) > 1:
        return None, (
            "Hay varios proveedores que coinciden ("
            + ", ".join(f"«{p['nombre']}»" for p in matches)
            + "). No guardé nada: preguntale al usuario cuál es."
        )
    return matches[0], None


def build_proveedor_tools(
    client: Client, acciones: list[str], turno: Turno | None = None
) -> list[BaseTool]:
    turno = turno or Turno()

    def _rubros() -> dict[int, str]:
        return {r["id"]: r["nombre"] for r in finanzas.list_rubros(client, incluir_inactivos=True)}

    def buscar_proveedor(texto: str | None = None, rubro: str | None = None) -> str:
        """Busca en la lista de proveedores del equipo. `texto` es parte del nombre,
        contacto o teléfono; `rubro` filtra por rubro (por ejemplo «Estructura»). Si hay
        uno solo, muestra su ficha: contacto, calificación (estrellas de los socios) y
        compras en todas las obras. Usala para teléfonos, mails, a quién llamar, qué tal
        es un proveedor o cuánto se le compró."""
        try:
            nombres_rubros = _rubros()
            rubro_id = None
            if rubro and rubro.strip():
                encontrados = finanzas.find_rubros(client, rubro)
                if not encontrados:
                    return f"No hay un rubro «{rubro}»."
                rubro_id = encontrados[0]["id"]
            lista = proveedores.filtrar(
                proveedores.list_proveedores(client), texto or "", rubro_id, nombres_rubros
            )
            if not lista:
                return "No hay proveedores que coincidan en la lista."
            calificaciones = proveedores.list_calificaciones(client)
            if len(lista) == 1:
                p = lista[0]
                propias = [c for c in calificaciones if c["proveedor_id"] == p["id"]]
                return turno.datos(
                    proveedores.describe_proveedor(
                        p, nombres_rubros, propias, proveedores.compras(client, p["id"])
                    )
                )
            promedios = proveedores.promedios(calificaciones)
            return turno.datos(
                "\n".join(
                    f"- {p['nombre']} · "
                    f"{proveedores.estrellas_txt(*promedios.get(p['id'], (None, 0)))}"
                    + (f" · {p['telefono']}" if p.get("telefono") else "")
                    for p in lista[:30]
                )
            )
        except (proveedores.ProveedoresError, finanzas.FinanzasError) as exc:
            return f"No se pudo leer la lista de proveedores: {exc}"

    def crear_proveedor(
        nombre: str,
        telefono: str | None = None,
        email: str | None = None,
        contacto: str | None = None,
        rubro: str | None = None,
    ) -> str:
        """Da de alta un proveedor en la lista del equipo. Usala SOLO si el usuario pide
        explícitamente dar de alta (agregar, crear) un proveedor, o confirma que querés
        darlo de alta después de que no lo encontraste. Nunca lo crees por tu cuenta."""
        if bloqueo := turno.bloqueo("di de alta el proveedor", PROVEEDOR):
            return bloqueo
        try:
            datos = {"nombre": nombre, "telefono": telefono, "email": email, "contacto": contacto}
            if rubro and rubro.strip():
                encontrados = finanzas.find_rubros(client, rubro)
                if encontrados:
                    datos["rubro_ids"] = [encontrados[0]["id"]]
            nuevo = proveedores.create_proveedor(client, datos)
        except (proveedores.ProveedoresError, finanzas.FinanzasError) as exc:
            return f"No se pudo dar de alta el proveedor: {exc}"
        acciones.append(f"🏢 Proveedor agregado: «{nuevo['nombre']}»")
        return f"Proveedor «{nuevo['nombre']}» agregado a la lista (#{nuevo['id']})."

    return [StructuredTool.from_function(fn) for fn in (buscar_proveedor, crear_proveedor)]
