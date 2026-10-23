"""🏷️ Rubros (#49, base of #24): the shared list every obra's budget uses.

List in order, add, move up or down, and deactivate or reactivate. Rubros are
never deleted (their ítems and gastos keep pointing at them).
"""

from __future__ import annotations

import streamlit as st

from atrium import finanzas
from ui_utils import texto_seguro

_AVISOS = "rubros_avisos"


def render_rubros_page(supabase) -> None:
    st.header("Rubros")
    st.caption(
        "La lista es compartida por todas las obras y define el orden del presupuesto. "
        "Un rubro desactivado no se ofrece para ítems nuevos; lo ya cargado se mantiene."
    )
    for tipo, mensaje in st.session_state.pop(_AVISOS, []):
        getattr(st, tipo)(mensaje)

    try:
        rubros = finanzas.list_rubros(supabase, incluir_inactivos=True)
    except finanzas.FinanzasError as exc:
        st.error(f"No se pudieron leer los rubros: {texto_seguro(exc)}")
        return

    _form_nuevo_rubro(supabase)

    for i, rubro in enumerate(rubros):
        _fila_rubro(supabase, rubro, primero=i == 0, ultimo=i == len(rubros) - 1)


def _fila_rubro(supabase, rubro: dict, primero: bool, ultimo: bool) -> None:
    rid = rubro["id"]
    activo = rubro.get("activo", True)
    with st.container(border=True, key=f"rubro_fila_{rid}"):
        c1, c2, c3, c4 = st.columns([5, 1, 1, 2], vertical_alignment="center")
        nombre = texto_seguro(rubro["nombre"])
        c1.markdown(f"**{nombre}**" if activo else f"~~{nombre}~~ · Desactivado")
        if c2.button(
            "↑",
            key=f"rubro_subir_{rid}",
            disabled=primero,
            help=f"Subir «{rubro['nombre']}» un lugar",
            width="stretch",
        ):
            _mover(supabase, rid, -1)
        if c3.button(
            "↓",
            key=f"rubro_bajar_{rid}",
            disabled=ultimo,
            help=f"Bajar «{rubro['nombre']}» un lugar",
            width="stretch",
        ):
            _mover(supabase, rid, 1)
        etiqueta = "Desactivar" if activo else "Reactivar"
        if c4.button(etiqueta, key=f"rubro_activo_{rid}", width="stretch"):
            try:
                finanzas.set_rubro_activo(supabase, rid, not activo)
            except finanzas.FinanzasError as exc:
                st.error(texto_seguro(exc))
                return
            estado = "desactivado" if activo else "reactivado"
            st.session_state[_AVISOS] = [
                ("success", f"Rubro «{texto_seguro(rubro['nombre'])}» {estado}.")
            ]
            st.rerun()


def _mover(supabase, rubro_id: int, paso: int) -> None:
    try:
        finanzas.mover_rubro(supabase, rubro_id, paso)
    except finanzas.FinanzasError as exc:
        st.error(texto_seguro(exc))
        return
    st.rerun()


def _form_nuevo_rubro(supabase) -> None:
    with st.form("nuevo_rubro"):
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        nombre = c1.text_input("Rubro nuevo (obligatorio)", key="rubro_nuevo_nombre")
        agregar = c2.form_submit_button("Agregar rubro", width="stretch")
    if agregar:
        try:
            creado = finanzas.create_rubro(supabase, nombre)
        except finanzas.FinanzasError as exc:
            st.error(texto_seguro(exc))  # the form keeps what was typed
            return
        st.session_state.pop("rubro_nuevo_nombre", None)
        st.session_state[_AVISOS] = [
            ("success", f"Rubro «{texto_seguro(creado['nombre'])}» agregado.")
        ]
        st.rerun()
