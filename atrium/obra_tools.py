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

from atrium import finanzas, obras

if TYPE_CHECKING:
    from supabase import Client


def build_obra_tools(
    client: Client,
    autor: str | None,
    obra_activa: Callable[[], int | None],
    acciones: list[str],
) -> list[BaseTool]:
    """Tools bound to one user. ``obra_activa`` returns the obra picked in the UI."""

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
            return obras.describe_obras(obras.list_obras(client, estado or None))
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
        return texto

    def agregar_nota_bitacora(nota: str, obra: str | None = None, fecha: str | None = None) -> str:
        """Agrega una nota a la bitácora de una obra. Usala SOLO si el usuario pide
        explícitamente anotar o registrar algo. `fecha` en formato AAAA-MM-DD (vacío = hoy)."""
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

    def _rubro(texto: str) -> tuple[dict | None, str | None]:
        matches = finanzas.find_rubros(client, texto)
        if len(matches) == 1:
            return matches[0], None
        disponibles = ", ".join(r["nombre"] for r in finanzas.list_rubros(client))
        if not matches:
            return None, (
                f"No hay un rubro «{texto}». Elegí el más adecuado entre: {disponibles}. "
                "Si ninguno corresponde, preguntale al usuario."
            )
        return None, (
            "Hay varios rubros que coinciden; elegí uno o preguntale al usuario: "
            + ", ".join(r["nombre"] for r in matches)
        )

    def registrar_gasto(
        monto: float,
        descripcion: str,
        rubro: str,
        moneda: str = "ARS",
        obra: str | None = None,
        fecha: str | None = None,
        proveedor: str | None = None,
    ) -> str:
        """Registra un gasto de una obra. Usala SOLO si el usuario pide explícitamente
        cargar o registrar un gasto. `monto` es un número (350 mil = 350000). `moneda`
        es ARS o USD. `rubro` es el nombre de un rubro existente (por ejemplo, el hierro
        va en Estructura). `fecha` en formato AAAA-MM-DD (vacío = hoy). La cotización
        del dólar MEP se completa sola."""
        try:
            encontrada, problema = _resolver(obra)
            if problema:
                return problema
            elegido, problema = _rubro(rubro)
            if problema:
                return problema
            gasto, aviso = finanzas.add_gasto(
                client,
                encontrada["id"],
                monto=monto,
                moneda=moneda,
                rubro_id=elegido["id"],
                descripcion=descripcion,
                fecha=fecha or None,
                proveedor=proveedor,
            )
        except (obras.ObrasError, finanzas.FinanzasError) as exc:
            return f"No se pudo registrar el gasto: {exc}"
        monto_txt = finanzas.formato_monto(gasto["monto"], gasto["moneda"])
        acciones.append(
            f"💸 Gasto registrado en «{encontrada['nombre']}»: {monto_txt} · {elegido['nombre']}"
        )
        texto = (
            f"Gasto registrado en {encontrada['nombre']}: {monto_txt}, rubro "
            f"{elegido['nombre']}, fecha {gasto['fecha']}"
        )
        if gasto.get("tipo_cambio"):
            texto += f", cotización MEP {finanzas.formato_numero(gasto['tipo_cambio'], 2)}."
        else:
            texto += f". {aviso}"
        return texto

    def resumen_plata(obra: str | None = None, moneda: str = "ARS") -> str:
        """Muestra presupuestado, gastado y desvío por rubro de una obra, en ARS o USD
        (dólar MEP). Usala para preguntas sobre plata, gastos, presupuesto o desvíos."""
        try:
            encontrada, problema = _resolver(obra)
            if problema:
                return problema
            res = finanzas.resumen(client, encontrada["id"], moneda)
        except (obras.ObrasError, finanzas.FinanzasError) as exc:
            return f"No se pudo calcular el resumen: {exc}"
        return finanzas.describe_resumen(res, encontrada["nombre"])

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
    ]
