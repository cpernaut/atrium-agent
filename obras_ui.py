"""Streamlit screens for the obras tracker. Data access lives in ``atrium.obras``."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from atrium import finanzas, obras
from plata_ui import render_plata
from ui_utils import texto_seguro

_SCHEMA_HINT = (
    "¿Ya corriste `supabase_schema.sql` en el SQL Editor de Supabase? "
    "Ahí se crean las tablas `obras` y `bitacora`."
)


def _load_obras(supabase) -> list[obras.Obra] | None:
    try:
        return obras.list_obras(supabase)
    except obras.ObrasError as exc:
        st.error(f"No se pudieron leer las obras: {exc}")
        st.caption(_SCHEMA_HINT)
        return None


def _label(obra: obras.Obra) -> str:
    return f"{obra['nombre']} (#{obra['id']})"


# --------------------------------------------------------------------------- #
# Sidebar: active obra for the agent
# --------------------------------------------------------------------------- #
def select_obra_activa(supabase) -> int | None:
    """Sidebar picker. The agent uses the chosen obra for normativa and notes."""

    try:
        lista = obras.list_obras(supabase)
    except obras.ObrasError:
        return None
    if not lista:
        return None
    opciones = [None, *(o["id"] for o in lista)]
    nombres = {o["id"]: _label(o) for o in lista}
    actual = st.session_state.get("obra_activa")
    elegida = st.selectbox(
        "Obra activa",
        opciones,
        index=opciones.index(actual) if actual in opciones else 0,
        format_func=lambda i: "— Ninguna —" if i is None else nombres[i],
        help="El agente responde la normativa del municipio de esta obra y anota en su bitácora.",
    )
    st.session_state.obra_activa = elegida
    return elegida


# --------------------------------------------------------------------------- #
# Obras page
# --------------------------------------------------------------------------- #
def render_obras_page(supabase, user) -> None:
    st.title("📋 Obras")
    tab_lista, tab_nueva, tab_bitacora, tab_plata = st.tabs(
        ["Obras", "Nueva obra", "Bitácora", "💰 Plata"]
    )
    lista = _load_obras(supabase)
    if lista is None:
        return

    with tab_lista:
        _render_lista(supabase, lista)
    with tab_nueva:
        _render_nueva(supabase)
    with tab_bitacora:
        _render_bitacora(supabase, user, lista)
    with tab_plata:
        render_plata(supabase, lista)


def _render_lista(supabase, lista: list[obras.Obra]) -> None:
    if not lista:
        st.info("Todavía no hay obras. Cargá la primera en «Nueva obra».")
        return

    df = pd.DataFrame(lista)
    c1, c2, c3 = st.columns(3)
    c1.metric("Obras", len(df))
    c2.metric("En curso", int((df["estado"] == "En curso").sum()))
    c3.metric("Avance promedio", f"{df['avance'].mean():.0f}%")

    filtro = st.multiselect("Filtrar por estado", obras.ESTADOS, key="lista_filtro")
    if filtro:
        df = df[df["estado"].isin(filtro)]
    columnas = [
        "nombre",
        "cliente",
        "municipio",
        "tipo",
        "estado",
        "avance",
        "responsable",
        "fecha_inicio",
        "fecha_fin_estimada",
        "presupuesto",
        "moneda",
    ]
    st.dataframe(
        df[[c for c in columnas if c in df.columns]],
        hide_index=True,
        width="stretch",
        column_config={
            "avance": st.column_config.ProgressColumn(
                "Avance", min_value=0, max_value=100, format="%d%%"
            ),
            "presupuesto": st.column_config.NumberColumn("Presupuesto", format="%.0f"),
        },
    )

    st.subheader("Actualizar estado")
    por_id = {o["id"]: o for o in lista}
    obra = por_id[
        st.selectbox(
            "Obra", list(por_id), format_func=lambda i: _label(por_id[i]), key="lista_obra"
        )
    ]
    with st.form("actualizar_obra"):
        actual = obra.get("estado")
        estado = st.selectbox(
            "Estado",
            obras.ESTADOS,
            index=obras.ESTADOS.index(actual) if actual in obras.ESTADOS else 0,
            key=f"upd_estado_{obra['id']}",
        )
        avance = st.slider(
            "Avance (%)", 0, 100, int(obra.get("avance") or 0), key=f"upd_avance_{obra['id']}"
        )
        if st.form_submit_button("Guardar cambios"):
            try:
                obras.update_obra(supabase, obra["id"], {"estado": estado, "avance": avance})
            except obras.ObrasError as exc:
                st.error(str(exc))
            else:
                st.toast("✅ Obra actualizada")
                st.rerun()


def _render_nueva(supabase) -> None:
    with st.form("nueva_obra", clear_on_submit=True):
        nombre = st.text_input("Nombre de la obra *", key="nueva_nombre")
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Cliente", key="nueva_cliente")
        responsable = c2.text_input("Responsable", key="nueva_responsable")
        c1, c2 = st.columns([2, 1])
        direccion = c1.text_input("Dirección", key="nueva_direccion")
        municipio = c2.selectbox(
            "Municipio",
            obras.MUNICIPIOS,
            help="Define qué código de edificación usa el agente.",
            key="nueva_municipio",
        )
        c1, c2 = st.columns(2)
        tipo = c1.selectbox("Tipo", obras.TIPOS, key="nueva_tipo")
        estado = c2.selectbox("Estado", obras.ESTADOS, key="nueva_estado")
        c1, c2 = st.columns(2)
        inicio = c1.date_input("Fecha de inicio", value=None, format="DD/MM/YYYY")
        fin = c2.date_input("Fin estimado", value=None, format="DD/MM/YYYY")
        c1, c2 = st.columns([3, 1])
        presupuesto = c1.number_input(
            "Presupuesto", min_value=0.0, step=1000.0, key="nueva_presupuesto"
        )
        moneda = c2.selectbox("Moneda", obras.MONEDAS, key="nueva_moneda")

        if st.form_submit_button("Crear obra"):
            try:
                creada = obras.create_obra(
                    supabase,
                    {
                        "nombre": nombre.strip(),
                        "cliente": cliente or None,
                        "responsable": responsable or None,
                        "direccion": direccion or None,
                        "municipio": municipio,
                        "tipo": tipo,
                        "estado": estado,
                        "fecha_inicio": inicio.isoformat() if inicio else None,
                        "fecha_fin_estimada": fin.isoformat() if fin else None,
                        "presupuesto": presupuesto or None,
                        "moneda": moneda,
                    },
                )
            except obras.ObrasError as exc:
                st.error(texto_seguro(exc))
            else:
                st.success(f"Obra «{texto_seguro(nombre.strip())}» creada.")
                _crear_imprevistos(supabase, creada)


def _crear_imprevistos(supabase, obra: obras.Obra) -> None:
    """#35 R12: every new obra starts with its «Imprevistos» budget item."""

    try:
        item, aviso = finanzas.crear_imprevistos(supabase, obra)
    except finanzas.FinanzasError as exc:
        st.warning(
            "⚠️ No se pudo crear el ítem «Imprevistos» del presupuesto: "
            f"{texto_seguro(exc)}. Podés agregarlo desde «+ Agregar ítem»."
        )
        return
    st.caption(
        "Presupuesto: se agregó el ítem «Imprevistos» por "
        f"{texto_seguro(finanzas.formato_monto(item['monto'], item['moneda']))} (10 % del "
        "presupuesto de la obra). Lo podés editar o borrar en 💰 Plata."
    )
    if aviso:
        st.caption(f"⚠️ {texto_seguro(aviso)}")


def _render_bitacora(supabase, user, lista: list[obras.Obra]) -> None:
    if not lista:
        st.info("Cargá una obra primero.")
        return
    por_id = {o["id"]: o for o in lista}
    obra_id = st.selectbox(
        "Obra", list(por_id), format_func=lambda i: _label(por_id[i]), key="bitacora_obra"
    )

    with st.form("nota_bitacora", clear_on_submit=True):
        fecha = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY", key="nota_fecha")
        nota = st.text_area("Nota de obra", key="nota_texto")
        if st.form_submit_button("Agregar nota"):
            try:
                obras.add_nota(supabase, obra_id, nota, autor=user.email, fecha=fecha)
            except obras.ObrasError as exc:
                st.error(str(exc))
            else:
                st.rerun()

    try:
        notas = obras.list_bitacora(supabase, obra_id)
    except obras.ObrasError as exc:
        st.error(str(exc))
        return
    if not notas:
        st.caption("Sin notas todavía. También podés pedirle al agente: «anotá en esta obra…».")
    for n in notas:
        autor = texto_seguro(n.get("autor") or "—")
        st.markdown(f"**{texto_seguro(n['fecha'])}** · {autor}  \n{texto_seguro(n['nota'])}")
        st.divider()
