"""LangChain tools that let the agent read and update the obras tracker.

``build_obra_tools`` closes over the signed-in user's Supabase client, so every
call goes through row-level security. Write tools record what they did in the
returned ``acciones`` list, which the UI shows under the answer.

Tools never raise: errors come back as text so the model can explain them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, StructuredTool

from atrium import finanzas, obras, proveedores
from atrium.guardia import Turno
from atrium.proveedor_tools import build_proveedor_tools, resolver_proveedor

if TYPE_CHECKING:
    from supabase import Client


def build_obra_tools(
    client: Client,
    autor: str | None,
    obra_activa: Callable[[], int | None],
    acciones: list[str],
    pedido: str = "",
) -> list[BaseTool]:
    """Tools bound to one user and one turn.

    ``obra_activa`` returns the obra picked in the UI; ``pedido`` is the user's
    message of this turn (see ``atrium.guardia``: stored data can't trigger writes).
    """

    turno = Turno(pedido=pedido)

    def _resolver(obra: str | None) -> tuple[obras.Obra | None, str | None]:
        """(obra, None) on a unique match, else (None, message for the model)."""

        if not obra or not obra.strip():
            obra_id = obra_activa()
            if obra_id is None:
                return None, "No indicaste la obra y no hay ninguna obra activa seleccionada."
            encontrada = obras.get_obra(client, obra_id)
            return (encontrada, None) if encontrada else (None, "La obra activa ya no existe.")
        matches = obras.find_obras(client, obra)
        if not matches:
            return None, f"No encontré ninguna obra que coincida con «{obra}»."
        if len(matches) > 1:
            return None, (
                "Hay varias obras que coinciden; pedile al usuario que elija:\n"
                + obras.describe_obras(matches)
            )
        return matches[0], None

    def listar_obras(estado: str | None = None) -> str:
        """Lista las obras del tracker. `estado` filtra opcionalmente: Planificación,
        En curso, Pausada, Terminada o Cancelada."""
        try:
            return turno.datos(obras.describe_obras(obras.list_obras(client, estado or None)))
        except obras.ObrasError as exc:
            return f"Error al leer las obras: {exc}"

    def ver_obra(obra: str | None = None) -> str:
        """Muestra la ficha de una obra y sus últimas notas de bitácora. `obra` es el
        nombre (o parte) o el número; vacío usa la obra activa."""
        try:
            encontrada, problema = _resolver(obra)
            if problema:
                return problema
            notas = obras.list_bitacora(client, encontrada["id"], limit=5)
        except obras.ObrasError as exc:
            return f"Error al leer la obra: {exc}"
        texto = obras.describe_obra(encontrada)
        if notas:
            texto += "\nÚltimas notas de bitácora:\n" + "\n".join(
                f"- {n['fecha']} ({n.get('autor') or 's/autor'}): {n['nota']}" for n in notas
            )
        return turno.datos(texto)

    def agregar_nota_bitacora(nota: str, obra: str | None = None, fecha: str | None = None) -> str:
        """Agrega una nota a la bitácora de una obra. Usala SOLO si el usuario pide
        explícitamente anotar o registrar algo. `fecha` en formato AAAA-MM-DD (vacío = hoy)."""
        if bloqueo := turno.bloqueo("guardé la nota"):
            return bloqueo
        try:
            encontrada, problema = _resolver(obra)
            if problema:
                return problema
            obras.add_nota(client, encontrada["id"], nota, autor=autor, fecha=fecha or None)
        except obras.ObrasError as exc:
            return f"No se pudo guardar la nota: {exc}"
        acciones.append(f"📝 Nota agregada a la bitácora de «{encontrada['nombre']}»")
        return f"Nota guardada en la bitácora de {encontrada['nombre']} (#{encontrada['id']})."

    def actualizar_obra(
        obra: str | None = None,
        avance: int | None = None,
        estado: str | None = None,
    ) -> str:
        """Actualiza el avance (0-100) y/o el estado de una obra. Usala SOLO si el
        usuario pide explícitamente cambiar esos datos."""
        if bloqueo := turno.bloqueo("actualicé la obra"):
            return bloqueo
        cambios: dict = {}
        if avance is not None:
            cambios["avance"] = avance
        if estado:
            cambios["estado"] = estado
        try:
            encontrada, problema = _resolver(obra)
            if problema:
                return problema
            obras.update_obra(client, encontrada["id"], cambios)
        except obras.ObrasError as exc:
            return f"No se pudo actualizar la obra: {exc}"
        detalle = ", ".join(f"{k} → {v}{'%' if k == 'avance' else ''}" for k, v in cambios.items())
        acciones.append(f"✏️ «{encontrada['nombre']}» actualizada: {detalle}")
        return f"Obra {encontrada['nombre']} actualizada: {detalle}."

    def _item(obra: obras.Obra, texto: str, rubro: str | None) -> tuple[dict | None, str | None]:
        """(item, None) on a unique match, else (None, message asking the user)."""

        matches = finanzas.find_items(client, obra["id"], texto, rubro)
        if len(matches) == 1:
            return matches[0], None
        vigentes = [
            i for i in finanzas.list_presupuesto(client, obra["id"]) if not i.get("anulado")
        ]
        if not matches:
            disponibles = ", ".join(_nombre_item(i) for i in vigentes) or "(no hay ítems)"
            imprevistos = finanzas.imprevistos_vigente(vigentes)
            sugerencia = " o si va a «Imprevistos»" if imprevistos else ""
            return None, (
                f"No registré el gasto: no hay ningún ítem del presupuesto que coincida con "
                f"«{texto}». Ítems de la obra: {disponibles}. Preguntale al usuario a qué ítem "
                f"va{sugerencia}. Nunca crees ítems por tu cuenta."
            )
        # #35: with several possible items the agent must ask, never pick one itself.
        return None, (
            "No registré el gasto: hay varios ítems que coinciden ("
            + ", ".join(_nombre_item(i) for i in matches)
            + "). Preguntale al usuario cuál corresponde antes de volver a intentarlo."
        )

    def _nombre_item(item: dict) -> str:
        return f"«{item.get('descripcion') or 'Sin descripción'}»"

    def registrar_gasto(
        monto: float,
        descripcion: str,
        item: str,
        moneda: str | None = None,
        rubro: str | None = None,
        obra: str | None = None,
        fecha: str | None = None,
        proveedor: str | None = None,
    ) -> str:
        """Registra un gasto en un ítem del presupuesto de una obra. Usala SOLO si el
        usuario pide explícitamente cargar o registrar un gasto. Todo gasto va a un
        ítem: `item` es la descripción (o parte) del ítem, por ejemplo «hierro» o
        «imprevistos»; `rubro` opcional ayuda a desambiguar. `monto` es un número
        (350 mil = 350000). `moneda` es ARS o USD (vacío = la del ítem). `fecha` en
        formato AAAA-MM-DD (vacío = hoy). La cotización del dólar MEP se completa sola.
        `proveedor` (opcional) tiene que estar en la lista de proveedores del equipo.
        Si hay varios ítems o proveedores posibles, o ninguno, no guarda nada y hay que
        preguntar."""
        if bloqueo := turno.bloqueo("registré el gasto"):
            return bloqueo
        try:
            encontrada, problema = _resolver(obra)
            if problema:
                return problema
            elegido, problema = _item(encontrada, item, rubro)
            if problema:
                return problema
            proveedor_id = None
            if proveedor and proveedor.strip():
                del_proveedor, problema = resolver_proveedor(client, proveedor)
                if problema:
                    return problema
                proveedor_id = del_proveedor["id"]
            gasto, aviso = finanzas.add_gasto(
                client,
                elegido["id"],
                monto=monto,
                moneda=moneda or elegido["moneda"],
                descripcion=descripcion,
                fecha=fecha or None,
                proveedor_id=proveedor_id,
            )
        except (obras.ObrasError, finanzas.FinanzasError, proveedores.ProveedoresError) as exc:
            return f"No se pudo registrar el gasto: {exc}"
        monto_txt = finanzas.formato_monto(gasto["monto"], gasto["moneda"])
        nombre = elegido.get("descripcion") or "Sin descripción"
        acciones.append(f"💸 Gasto registrado en «{encontrada['nombre']}»: {monto_txt} · {nombre}")
        texto = (
            f"Gasto registrado en {encontrada['nombre']}: {monto_txt}, ítem {nombre}, "
            f"fecha {gasto['fecha']}"
        )
        if gasto.get("tipo_cambio"):
            texto += f", cotización MEP {finanzas.formato_numero(gasto['tipo_cambio'], 2)}."
        else:
            texto += f". {aviso}"
        return texto

    def resumen_plata(obra: str | None = None, moneda: str = "ARS") -> str:
        """Muestra presupuestado, gastado y desvío por rubro y por ítem del presupuesto de
        una obra, en ARS o USD (dólar MEP). Usala para preguntas sobre plata, gastos,
        presupuesto, saldos o desvíos."""
        try:
            encontrada, problema = _resolver(obra)
            if problema:
                return problema
            res = finanzas.resumen(client, encontrada["id"], moneda)
        except (obras.ObrasError, finanzas.FinanzasError) as exc:
            return f"No se pudo calcular el resumen: {exc}"
        return turno.datos(finanzas.describe_resumen(res, encontrada["nombre"]))

    return [
        StructuredTool.from_function(fn)
        for fn in (
            listar_obras,
            ver_obra,
            agregar_nota_bitacora,
            actualizar_obra,
            registrar_gasto,
            resumen_plata,
        )
    ] + build_proveedor_tools(client, acciones, turno)
