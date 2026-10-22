"""Streamlit screen for F-03 · Presupuesto y gastos (tab «💰 Plata» in Obras).

Accessibility: every input has a visible label, required fields say so,
status is always written in words (never color alone), amounts use es-AR
formatting with their currency, and user text is escaped before rendering.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from atrium import finanzas, obras
from ui_utils import texto_seguro

_SCHEMA_HINT = (
    "¿Ya corriste el `supabase_schema.sql` actualizado en Supabase? Ahí se crean las "
    "tablas `rubros`, `presupuesto_items` y `gastos`."
)
_FLASH = "plata_flash"
# Input limits matching the database columns (numeric(14,2) and numeric(12,4)).
_MONTO_MAX = 999_999_999_999.0
_TC_MAX = 99_999_999.0
_ULTIMOS = 20


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _flash(tipo: str, mensaje: str) -> None:
    """Message to show after the rerun that follows a save."""

    st.session_state.setdefault(_FLASH, []).append((tipo, mensaje))


def _show_flash() -> None:
    for tipo, mensaje in st.session_state.pop(_FLASH, []):
        getattr(st, tipo)(mensaje)


def _clear(keys: list[str]) -> None:
    """Empty a form after a successful save (must run before its widgets exist)."""

    for key in keys:
        st.session_state.pop(key, None)


def _clear_prefix(prefijo: str) -> None:
    """Uncheck every per-record confirmation (keys like ``anular_gasto_ok_12``)."""

    for key in [k for k in st.session_state if str(k).startswith(prefijo)]:
        st.session_state.pop(key, None)


def _cotizacion_txt(fila: dict) -> str:
    if not fila.get("tipo_cambio"):
        return "sin cotización"
    origen = "corregida a mano" if fila.get("tipo_cambio_origen") == "manual" else "automática"
    return f"MEP {finanzas.formato_numero(fila['tipo_cambio'], 2)} ({origen})"


def _fecha_txt(valor: str) -> str:
    return f"{valor[8:10]}/{valor[5:7]}/{valor[0:4]}" if valor and len(valor) >= 10 else "—"


def _rubro_nombre(rubros_por_id: dict, rubro_id) -> str:
    return rubros_por_id.get(rubro_id, {}).get("nombre", f"Rubro #{rubro_id}")


def _gasto_label(g: dict, rubros_por_id: dict) -> str:
    return (
        f"{_fecha_txt(g['fecha'])} · {finanzas.formato_monto(g['monto'], g['moneda'])} · "
        f"{_rubro_nombre(rubros_por_id, g['rubro_id'])} · {g['descripcion']}"
    )


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
def render_plata(supabase, lista: list[obras.Obra]) -> None:
    if not lista:
        st.info("Cargá una obra primero.")
        return

    por_id = {o["id"]: o for o in lista}
    c1, c2 = st.columns([3, 2])
    obra_id = c1.selectbox(
        "Obra",
        list(por_id),
        format_func=lambda i: f"{por_id[i]['nombre']} (#{i})",
        key="plata_obra",
    )
    moneda = c2.radio(
        "Ver montos en",
        finanzas.MONEDAS,
        horizontal=True,
        key="plata_moneda",
        help="USD usa la cotización del dólar MEP guardada en cada gasto e ítem.",
    )

    _show_flash()
    try:
        rubros = finanzas.list_rubros(supabase, incluir_inactivos=True)
        items = finanzas.list_presupuesto(supabase, obra_id)
        gastos = finanzas.list_gastos(supabase, obra_id)
    except finanzas.FinanzasError as exc:
        st.error(f"No se pudieron leer los datos de plata: {texto_seguro(exc)}")
        st.caption(_SCHEMA_HINT)
        return

    rubros_por_id = {r["id"]: r for r in rubros}
    activos = [r for r in rubros if r.get("activo", True)]
    resumen = finanzas.calcular_resumen(items, gastos, rubros, moneda)

    _render_totales(resumen)
    _render_tabla(resumen)
    _render_form_gasto(supabase, obra_id, activos)
    _render_gastos(supabase, gastos, rubros_por_id)
    _render_presupuesto(supabase, items, activos, rubros, rubros_por_id, obra_id, moneda)


def _render_totales(res: finanzas.Resumen) -> None:
    m = res.moneda
    c1, c2, c3 = st.columns(3)
    c1.metric("Presupuestado", finanzas.formato_monto(res.presupuestado, m))
    c2.metric(
        "Gastado",
        finanzas.formato_monto(res.gastado, m),
        help=f"Ejecutado: {finanzas.formato_porcentaje(res.ejecutado)} del presupuesto.",
    )
    estado = finanzas.estado_desvio(res.desvio, res.presupuestado)
    c3.metric(
        "Desvío",
        finanzas.formato_monto(res.desvio, m),
        help="Gastado menos presupuestado. Positivo significa que se gastó más de lo previsto.",
    )
    icono = {"Excedido": "🔴", "Dentro del presupuesto": "🟢"}.get(estado, "⚪")
    c3.caption(f"{icono} {estado}")
    if res.incompleto:
        st.warning(
            f"⚠️ Total incompleto: {len(res.sin_convertir)} registro(s) sin cotización no se "
            f"pudieron pasar a {m}. Cargá la cotización en «Corregir o anular un gasto» "
            "o con «Editar» en el ítem del presupuesto."
        )


def _render_tabla(res: finanzas.Resumen) -> None:
    if not res.filas:
        st.info("Todavía no hay presupuesto ni gastos en esta obra.")
        return
    m = res.moneda
    df = pd.DataFrame(
        [
            {
                # Estado right after Rubro: on a phone it stays visible without scrolling.
                "Rubro": f.rubro,
                "Estado": finanzas.estado_desvio(f.desvio, f.presupuestado),
                "Presupuestado": finanzas.formato_monto(f.presupuestado, m),
                "Gastado": finanzas.formato_monto(f.gastado, m),
                "Desvío": finanzas.formato_monto(f.desvio, m),
                "Ejecutado": None if f.ejecutado is None else float(f.ejecutado * 100),
            }
            for f in res.filas
        ]
    )
    st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        column_config={
            "Ejecutado": st.column_config.ProgressColumn(
                "Ejecutado", min_value=0, max_value=100, format="%.0f%%"
            ),
        },
    )


# --------------------------------------------------------------------------- #
# Gastos
# --------------------------------------------------------------------------- #
_GASTO_KEYS = [
    "gasto_monto",
    "gasto_rubro",
    "gasto_descripcion",
    "gasto_proveedor",
    "gasto_tc",
    "gasto_fecha",
]


def _render_form_gasto(supabase, obra_id: int, activos: list[dict]) -> None:
    st.subheader("Registrar un gasto")
    if st.session_state.pop("gasto_limpiar", False):
        _clear(_GASTO_KEYS)
    with st.form("nuevo_gasto"):
        c1, c2 = st.columns([3, 1])
        monto = c1.number_input(
            "Monto (obligatorio)",
            min_value=0.0,
            max_value=_MONTO_MAX,
            step=1000.0,
            format="%.2f",
            key="gasto_monto",
        )
        moneda = c2.selectbox("Moneda", finanzas.MONEDAS, key="gasto_moneda")
        rubro_id = st.selectbox(
            "Rubro (obligatorio)",
            [r["id"] for r in activos],
            index=None,  # R8: sin valor por defecto, así nadie clasifica mal por olvido
            placeholder="Elegí un rubro",
            format_func=lambda i: next(r["nombre"] for r in activos if r["id"] == i),
            key="gasto_rubro",
        )
        descripcion = st.text_input(
            "Descripción (obligatoria)",
            max_chars=200,
            placeholder="Ej.: hierro del 8 para la platea",
            key="gasto_descripcion",
        )
        with st.expander("Más datos: fecha, proveedor y cotización"):
            fecha = st.date_input(
                "Fecha del gasto",
                value=finanzas.hoy(),
                max_value=finanzas.hoy(),
                format="DD/MM/YYYY",
                key="gasto_fecha",
            )
            proveedor = st.text_input("Proveedor", max_chars=120, key="gasto_proveedor")
            tc = st.number_input(
                "Cotización del dólar (opcional)",
                min_value=0.0,
                max_value=_TC_MAX,
                step=1.0,
                format="%.2f",
                key="gasto_tc",
                help="Dejala en 0 para usar el dólar MEP promedio de la fecha, automático.",
            )
        if st.form_submit_button("Guardar gasto", type="primary"):
            try:
                gasto, aviso = finanzas.add_gasto(
                    supabase,
                    obra_id,
                    monto=monto,
                    moneda=moneda,
                    rubro_id=rubro_id,
                    descripcion=descripcion,
                    fecha=fecha,
                    proveedor=proveedor,
                    tipo_cambio=tc or None,
                )
            except finanzas.FinanzasError as exc:
                st.error(f"No se guardó el gasto: {texto_seguro(exc)}")
            else:
                _flash(
                    "success",
                    "✅ Gasto guardado: "
                    + texto_seguro(
                        f"{finanzas.formato_monto(gasto['monto'], gasto['moneda'])}"
                        f" · {_cotizacion_txt(gasto)}."
                    ),
                )
                if aviso:
                    _flash("warning", f"⚠️ {texto_seguro(aviso)}")
                st.session_state["gasto_limpiar"] = True
                st.rerun()


def _render_gastos(supabase, gastos: list[dict], rubros_por_id: dict) -> None:
    st.subheader("Últimos gastos")
    if not gastos:
        st.caption("Todavía no hay gastos en esta obra.")
        return
    for g in gastos[:_ULTIMOS]:
        linea = (
            f"{texto_seguro(_fecha_txt(g['fecha']))} · "
            f"**{texto_seguro(finanzas.formato_monto(g['monto'], g['moneda']))}** · "
            f"{texto_seguro(_rubro_nombre(rubros_por_id, g['rubro_id']))} · "
            f"{texto_seguro(g['descripcion'])}"
        )
        if g.get("proveedor"):
            linea += f" · {texto_seguro(g['proveedor'])}"
        detalle = texto_seguro(_cotizacion_txt(g))
        if g.get("anulado"):
            st.markdown(f"~~{linea}~~ — **Anulado**")
        else:
            st.markdown(f"{linea}  \n{detalle}")
    if len(gastos) > _ULTIMOS:
        st.caption(f"Se muestran los últimos {_ULTIMOS} de {len(gastos)} gastos.")

    vigentes = [g for g in gastos if not g.get("anulado")]
    if not vigentes:
        return
    por_id = {g["id"]: g for g in vigentes}
    if st.session_state.pop("anular_gasto_limpiar", False):
        _clear(["tc_gasto_valor"])
        _clear_prefix("anular_gasto_ok_")
    with st.expander("Corregir o anular un gasto"):
        gasto_id = st.selectbox(
            "Gasto",
            list(por_id),
            format_func=lambda i: _gasto_label(por_id[i], rubros_por_id),
            key="gasto_elegido",
        )
        with st.form("corregir_tc"):
            st.markdown(f"Cotización actual: {texto_seguro(_cotizacion_txt(por_id[gasto_id]))}")
            valor = st.number_input(
                "Nueva cotización del dólar (pesos por dólar)",
                min_value=0.0,
                max_value=_TC_MAX,
                step=1.0,
                format="%.2f",
                key="tc_gasto_valor",
            )
            if st.form_submit_button("Guardar cotización"):
                try:
                    finanzas.set_tipo_cambio(supabase, "gastos", gasto_id, valor)
                except finanzas.FinanzasError as exc:
                    st.error(f"No se guardó la cotización: {texto_seguro(exc)}")
                else:
                    _flash("success", "✅ Cotización corregida a mano.")
                    st.session_state["anular_gasto_limpiar"] = True
                    st.rerun()
        with st.form("anular_gasto"):
            # The confirmation belongs to the selected gasto: picking another one
            # starts unchecked, so a stale tick can't cancel the wrong record.
            confirmado = st.checkbox(
                "Confirmo que quiero anular este gasto (deja de sumar, pero no se borra)",
                key=f"anular_gasto_ok_{gasto_id}",
            )
            if st.form_submit_button("Anular gasto"):
                if not confirmado:
                    st.error("Marcá la confirmación para anular el gasto.")
                else:
                    try:
                        finanzas.anular_gasto(supabase, gasto_id)
                    except finanzas.FinanzasError as exc:
                        st.error(f"No se anuló el gasto: {texto_seguro(exc)}")
                    else:
                        _flash("success", "✅ Gasto anulado.")
                        st.session_state["anular_gasto_limpiar"] = True
                        st.rerun()


# --------------------------------------------------------------------------- #
# Presupuesto (F-03 R8-R10): lista por rubro, detalle, alta, edición y borrado
# --------------------------------------------------------------------------- #
_NUEVO_ABIERTO = "item_nuevo_abierto"
_EDITANDO = "item_editando"
_A_BORRAR = "item_a_borrar"
_NUEVO = "nuevo_item_"  # prefix of the new-item form widgets


def _editar_prefijo(item_id: int) -> str:
    return f"editar_item_{item_id}_"


def _item_titulo(item: dict) -> str:
    descripcion = item.get("descripcion") or "Sin descripción"
    return f"{descripcion} — {finanzas.formato_monto(item['monto'], item['moneda'])}"


def _render_presupuesto(
    supabase,
    items: list[dict],
    activos: list[dict],
    rubros: list[dict],
    rubros_por_id: dict,
    obra_id: int,
    moneda_vista: str,
) -> None:
    st.subheader("Presupuesto de la obra")
    vigentes = [i for i in items if not i.get("anulado")]

    if st.session_state.get(_NUEVO_ABIERTO):
        _form_nuevo_item(supabase, obra_id, activos)
    elif st.button("+ Agregar ítem", key="item_agregar"):
        _clear_prefix(_NUEVO)  # R8: siempre vacío al abrir
        st.session_state[_NUEVO_ABIERTO] = True
        st.rerun()

    if not vigentes:
        st.caption("Todavía no hay ítems en el presupuesto de esta obra.")
        st.session_state.pop(_A_BORRAR, None)
        return

    orden = {r["id"]: (r.get("orden", 10**6), finanzas.normalizar(r["nombre"])) for r in rubros}
    grupos: dict[int, list[dict]] = {}
    for item in vigentes:
        grupos.setdefault(item["rubro_id"], []).append(item)

    for rubro_id in sorted(grupos, key=lambda r: orden.get(r, (10**6, ""))):
        del_rubro = grupos[rubro_id]
        resumen = finanzas.calcular_resumen(del_rubro, [], rubros, moneda_vista)
        subtotal = finanzas.formato_monto(resumen.presupuestado, moneda_vista)
        cantidad = f"{len(del_rubro)} ítem" + ("" if len(del_rubro) == 1 else "s")
        with st.container(border=True):
            encabezado = (
                f"**{texto_seguro(_rubro_nombre(rubros_por_id, rubro_id))}** · "
                f"{texto_seguro(cantidad)} · Subtotal {texto_seguro(subtotal)}"
            )
            if resumen.incompleto:
                encabezado += f" · {len(resumen.sin_convertir)} sin cotización"
            st.markdown(encabezado)
            for item in del_rubro:
                _render_item(supabase, item, activos, rubros_por_id)

    pendiente = st.session_state.get(_A_BORRAR)
    if pendiente is not None:
        item = next((i for i in vigentes if i["id"] == pendiente), None)
        if item is None:
            st.session_state.pop(_A_BORRAR, None)
        else:
            _dialogo_borrar(supabase, item, rubros_por_id)


def _render_item(supabase, item: dict, activos: list[dict], rubros_por_id: dict) -> None:
    item_id = item["id"]
    editando = st.session_state.get(_EDITANDO) == item_id
    with st.expander(texto_seguro(_item_titulo(item)), expanded=editando):
        if editando:
            _form_editar_item(supabase, item, activos, rubros_por_id)
            return
        detalle = [
            ("Rubro", _rubro_nombre(rubros_por_id, item["rubro_id"])),
            ("Descripción", item.get("descripcion") or "—"),
            ("Monto", finanzas.formato_monto(item["monto"], item["moneda"])),
            ("Fecha de carga", _fecha_txt(item.get("fecha") or "")),
            ("Cotización", _cotizacion_txt(item)),
        ]
        st.markdown("\n".join(f"- **{campo}:** {texto_seguro(valor)}" for campo, valor in detalle))
        c1, c2 = st.columns(2)
        if c1.button("Editar", key=f"item_editar_{item_id}", width="stretch"):
            _clear_prefix(_editar_prefijo(item_id))  # arranca con los valores actuales
            st.session_state[_EDITANDO] = item_id
            st.rerun()
        if c2.button("Borrar", key=f"item_borrar_{item_id}", width="stretch"):
            st.session_state[_A_BORRAR] = item_id
            st.rerun()


def _faltantes(rubro_id, moneda, monto) -> list[str]:
    faltan = []
    if rubro_id is None:
        faltan.append("elegí un rubro")
    if not moneda:
        faltan.append("elegí la moneda")
    if monto is None:
        faltan.append("ingresá el monto")
    return faltan


def _form_nuevo_item(supabase, obra_id: int, activos: list[dict]) -> None:
    with st.form("form_nuevo_item", border=True):
        st.markdown("**Nuevo ítem del presupuesto**")
        rubro_id = st.selectbox(
            "Rubro (obligatorio)",
            [r["id"] for r in activos],
            index=None,
            placeholder="Elegí un rubro",
            format_func=lambda i: next(r["nombre"] for r in activos if r["id"] == i),
            key=f"{_NUEVO}rubro",
        )
        descripcion = st.text_input(
            "Descripción",
            max_chars=200,
            placeholder="Ej.: platea de 80 m²",
            key=f"{_NUEVO}descripcion",
        )
        c1, c2 = st.columns([3, 2])
        monto = c1.number_input(
            "Monto (obligatorio)",
            min_value=0.0,
            max_value=_MONTO_MAX,
            value=None,
            step=1000.0,
            format="%.2f",
            placeholder="0,00",
            key=f"{_NUEVO}monto",
        )
        moneda = c2.radio(
            "Moneda (obligatoria)",
            finanzas.MONEDAS,
            index=None,
            horizontal=True,
            key=f"{_NUEVO}moneda",
        )
        tc = st.number_input(
            "Cotización del dólar (opcional)",
            min_value=0.0,
            max_value=_TC_MAX,
            value=None,
            step=1.0,
            format="%.2f",
            placeholder="Automática: MEP de hoy",
            key=f"{_NUEVO}tc",
            help="Dejala vacía para usar el dólar MEP promedio de hoy.",
        )
        b1, b2 = st.columns(2)
        agregar = b1.form_submit_button(
            "Agregar", type="primary", width="stretch", key="item_nuevo_agregar"
        )
        cancelar = b2.form_submit_button("Cancelar", width="stretch", key="item_nuevo_cancelar")

    if cancelar:
        st.session_state.pop(_NUEVO_ABIERTO, None)
        _clear_prefix(_NUEVO)
        st.rerun()
    if not agregar:
        return
    faltan = _faltantes(rubro_id, moneda, monto)
    if faltan:
        st.error("No se agregó el ítem: " + ", ".join(faltan) + ".")
        return
    try:
        item, aviso = finanzas.add_presupuesto_item(
            supabase,
            obra_id,
            monto=monto,
            moneda=moneda,
            rubro_id=rubro_id,
            descripcion=descripcion,
            tipo_cambio=tc or None,
        )
    except finanzas.FinanzasError as exc:
        st.error(f"No se agregó el ítem: {texto_seguro(exc)}")
        return
    rubro = next((r["nombre"] for r in activos if r["id"] == item["rubro_id"]), "")
    _flash(
        "success",
        "✅ Ítem agregado: "
        + texto_seguro(f"{rubro} · {finanzas.formato_monto(item['monto'], item['moneda'])}."),
    )
    if aviso:
        _flash("warning", f"⚠️ {texto_seguro(aviso)}")
    st.session_state.pop(_NUEVO_ABIERTO, None)
    _clear_prefix(_NUEVO)
    st.rerun()


def _form_editar_item(supabase, item: dict, activos: list[dict], rubros_por_id: dict) -> None:
    item_id = item["id"]
    prefijo = _editar_prefijo(item_id)
    opciones = [r["id"] for r in activos]
    if item["rubro_id"] not in opciones:  # rubro desactivado después: se puede conservar
        opciones.insert(0, item["rubro_id"])
    tc_actual = float(item["tipo_cambio"]) if item.get("tipo_cambio") else None

    with st.form(f"form_editar_item_{item_id}", border=False):
        st.markdown("**Editar ítem**")
        rubro_id = st.selectbox(
            "Rubro (obligatorio)",
            opciones,
            index=opciones.index(item["rubro_id"]),
            format_func=lambda i: _rubro_nombre(rubros_por_id, i),
            key=f"{prefijo}rubro",
        )
        descripcion = st.text_input(
            "Descripción",
            value=item.get("descripcion") or "",
            max_chars=200,
            key=f"{prefijo}descripcion",
        )
        c1, c2 = st.columns([3, 2])
        monto = c1.number_input(
            "Monto (obligatorio)",
            min_value=0.0,
            max_value=_MONTO_MAX,
            value=float(item["monto"]),
            step=1000.0,
            format="%.2f",
            key=f"{prefijo}monto",
        )
        moneda = c2.radio(
            "Moneda (obligatoria)",
            finanzas.MONEDAS,
            index=list(finanzas.MONEDAS).index(item["moneda"]),
            horizontal=True,
            key=f"{prefijo}moneda",
        )
        tc = st.number_input(
            "Cotización del dólar",
            min_value=0.0,
            max_value=_TC_MAX,
            value=tc_actual,
            step=1.0,
            format="%.2f",
            placeholder="Sin cotización",
            key=f"{prefijo}tc",
            help="Si la cambiás, queda marcada como corregida a mano.",
        )
        b1, b2 = st.columns(2)
        guardar = b1.form_submit_button(
            "Guardar cambios", type="primary", width="stretch", key=f"item_guardar_{item_id}"
        )
        cancelar = b2.form_submit_button(
            "Cancelar", width="stretch", key=f"item_cancelar_{item_id}"
        )

    if cancelar:
        st.session_state.pop(_EDITANDO, None)
        _clear_prefix(prefijo)
        st.rerun()
    if not guardar:
        return
    faltan = _faltantes(rubro_id, moneda, monto)
    if faltan:
        st.error("No se guardaron los cambios: " + ", ".join(faltan) + ".")
        return
    try:
        finanzas.update_presupuesto_item(
            supabase,
            item_id,
            monto=monto,
            moneda=moneda,
            rubro_id=rubro_id,
            descripcion=descripcion,
            tipo_cambio=tc or None,
        )
    except finanzas.FinanzasError as exc:
        st.error(f"No se guardaron los cambios: {texto_seguro(exc)}")
        return
    _flash("success", "✅ Cambios guardados.")
    st.session_state.pop(_EDITANDO, None)
    _clear_prefix(prefijo)
    st.rerun()


def _cancelar_borrado() -> None:
    st.session_state.pop(_A_BORRAR, None)


def _dialogo_borrar(supabase, item: dict, rubros_por_id: dict) -> None:
    """R10: confirm in a dialog that names the item; «Borrar» hides it and keeps it."""

    @st.dialog("¿Borrar este ítem del presupuesto?", on_dismiss=_cancelar_borrado)
    def dialogo() -> None:
        rubro = _rubro_nombre(rubros_por_id, item["rubro_id"])
        st.markdown(
            f"Vas a borrar **{texto_seguro(item.get('descripcion') or 'Sin descripción')}** "
            f"de **{texto_seguro(rubro)}** por "
            f"**{texto_seguro(finanzas.formato_monto(item['monto'], item['moneda']))}**."
        )
        st.markdown(
            "Deja de sumar en el presupuesto y en los totales. Queda guardado en el "
            "historial de la obra."
        )
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key="item_borrar_cancelar", width="stretch"):
            _cancelar_borrado()
            st.rerun()
        if c2.button("Borrar ítem", key="item_borrar_confirmar", type="primary", width="stretch"):
            try:
                finanzas.borrar_presupuesto_item(supabase, item["id"])
            except finanzas.FinanzasError as exc:
                st.error(f"No se borró el ítem: {texto_seguro(exc)}")
                return
            if st.session_state.get(_EDITANDO) == item["id"]:
                st.session_state.pop(_EDITANDO, None)
            _cancelar_borrado()
            _flash("success", "✅ Ítem borrado del presupuesto.")
            st.rerun()

    dialogo()
