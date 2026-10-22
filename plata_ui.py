"""Streamlit screen for F-03 · Presupuesto y gastos (tab «💰 Plata» in Obras).

The budget is a list of items grouped by rubro; every gasto belongs to an item
and is added, listed and cancelled inside it (#35).

Accessibility: every input has a visible label, required fields say so,
status is always written in words (never color alone), amounts use es-AR
formatting with their currency, and user text is escaped before rendering.
"""

from __future__ import annotations

import streamlit as st

from atrium import finanzas
from ui_utils import texto_seguro

_SCHEMA_HINT = (
    "¿Ya corriste el `supabase_schema.sql` actualizado en Supabase? Ahí se crean las "
    "tablas `rubros`, `presupuesto_items` y `gastos`."
)
_FLASH = "plata_flash"
# Input limits matching the database columns (numeric(14,2) and numeric(12,4)).
_MONTO_MAX = 999_999_999_999.0
_TC_MAX = 99_999_999.0


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
    """Forget every widget whose key starts with ``prefijo`` (empties a form)."""

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


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
def render_plata(supabase, obra_id: int | None) -> None:
    """Budget of the obra chosen at the top of the page (one picker for the app, UX-02)."""

    if obra_id is None:
        st.info("Cargá una obra primero.")
        return

    moneda = st.radio(
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
        # Once per session and obra: if the MEP source is down, don't retry on every rerun.
        intentadas = st.session_state.setdefault("imprevistos_cotizados", set())
        if obra_id not in intentadas:
            intentadas.add(obra_id)
            items = finanzas.completar_cotizacion_imprevistos(supabase, items)
        gastos = finanzas.list_gastos(supabase, obra_id)
    except finanzas.FinanzasError as exc:
        st.error(f"No se pudieron leer los datos de plata: {texto_seguro(exc)}")
        st.caption(_SCHEMA_HINT)
        return

    rubros_por_id = {r["id"]: r for r in rubros}
    activos = [r for r in rubros if r.get("activo", True)]
    resumen = finanzas.calcular_resumen(items, gastos, rubros, moneda)

    _render_totales(resumen)
    _render_presupuesto(supabase, items, gastos, activos, rubros, rubros_por_id, obra_id, moneda)


def _render_totales(res: finanzas.Resumen) -> None:
    m = res.moneda
    c1, c2, c3 = st.columns(3)
    c1.metric("Presupuestado", finanzas.formato_monto(res.presupuestado, m))
    c2.metric(
        "Gastado",
        finanzas.formato_monto(res.gastado, m),
        help=f"Ejecutado: {finanzas.formato_porcentaje(res.ejecutado)} del presupuesto.",
    )
    c3.metric(
        "Desvío",
        finanzas.formato_monto(res.desvio, m),
        help="Gastado menos presupuestado. Positivo significa que se gastó más de lo previsto.",
    )
    c3.caption(finanzas.estado_con_icono(res.gastado, res.presupuestado))
    if res.incompleto:
        st.warning(
            f"⚠️ Total incompleto: {len(res.sin_convertir)} registro(s) sin cotización no se "
            f"pudieron pasar a {m}. Cargá la cotización con el lápiz ✏️ del gasto o del "
            "ítem en la tabla del presupuesto."
        )


# --------------------------------------------------------------------------- #
# Presupuesto (F-03 R8-R16): ítems por rubro y, dentro de cada uno, sus gastos
# --------------------------------------------------------------------------- #
_NUEVO_ABIERTO = "item_nuevo_abierto"
_EDITANDO = "item_editando"
_A_BORRAR = "item_a_borrar"
_NUEVO = "nuevo_item_"  # prefix of the new-item form widgets
_GASTO_ABIERTO = "gasto_nuevo_item"  # id of the item whose «Registrar un gasto» form is open
_GASTO_A_ANULAR = "gasto_a_anular"
_GASTO_TC = "gasto_tc_abierto"  # id of the gasto whose rate is being corrected


def _editar_prefijo(item_id: int) -> str:
    return f"editar_item_{item_id}_"


def _gasto_prefijo(item_id: int) -> str:
    return f"nuevo_gasto_{item_id}_"


def _item_nombre(item: dict) -> str:
    return item.get("descripcion") or "Sin descripción"


_RUBROS_ACTIVOS = "presupuesto_rubros_activos"  # options of the new-item form
_ABIERTOS = "presupuesto_abiertos"  # expanded rows: {"r12", "i34"} (rubro / ítem)

# Columns of the table (#45): same as the old per-rubro table, plus Ítems and
# % consumido, and the actions of each row.
COLUMNAS = (
    "Rubro / ítem / gasto",
    "Ítems",
    "Presupuestado",
    "Gastado",
    "Desvío",
    "% consumido",
    "Estado",
    "Acciones",
)
_ANCHOS = [3.0, 0.6, 1.6, 1.6, 1.5, 1.0, 1.9, 1.4]

_CSS_TABLA = """
<style>
/* One row = one horizontal block; on phones the table scrolls sideways
   instead of stacking the columns. */
.st-key-tabla_presupuesto { overflow-x: auto; }
.st-key-tabla_presupuesto [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap; min-width: 860px; gap: 0.5rem; align-items: center;
    border-bottom: 1px solid #E4E8EC; padding: 0.15rem 0;
}
.st-key-tabla_presupuesto [data-testid="stColumn"] { min-width: 0; }
/* The action icons are a horizontal block too: no row width, no row border. */
.st-key-tabla_presupuesto [class*="st-key-acciones_"],
.st-key-tabla_presupuesto [class*="st-key-acciones_"] [data-testid="stHorizontalBlock"] {
    min-width: 0 !important; border-bottom: none !important; padding: 0 !important;
    flex-wrap: nowrap;
}
.st-key-tabla_presupuesto [data-testid="stMarkdownContainer"] p { margin: 0; font-size: 0.88rem; }
/* Streamlit gives text a negative bottom margin (to cancel the paragraph's);
   without the paragraph margin, the cell would be shorter than its text and a
   second line (the original currency) would spill over the row's border. */
.st-key-tabla_presupuesto [data-testid="stMarkdown"],
.st-key-tabla_presupuesto [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
.st-key-tabla_presupuesto button p { font-size: 0.88rem; }
.st-key-tabla_presupuesto [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    min-width: 0; border-bottom: none;
}
.st-key-tabla_cabecera p { font-size: 0.78rem !important; color: #52606D; }
/* Indent only the first column, so the value columns stay aligned. */
[class*="st-key-nivel_item_"] [data-testid="stColumn"]:first-child { padding-left: 1.25rem; }
[class*="st-key-nivel_gasto_"] [data-testid="stColumn"]:first-child { padding-left: 2.5rem; }
[class*="st-key-nivel_gasto_detalle_"] { padding-left: 2.5rem; }
[class*="st-key-nivel_rubro_"] { background: #F3F5F7; border-radius: 6px; }
/* Small icon buttons for the row actions. */
.st-key-tabla_presupuesto button[kind="tertiary"] { padding: 0 0.25rem; min-height: 1.8rem; }
</style>
"""


def _abrir_alta(rubro_id: int | None) -> None:
    """Open the new-item form: empty (R8), or with ``rubro_id`` chosen (row «＋»).

    Runs as a button callback, before any widget is drawn, so switching from one
    open form to another can preset its fields.
    """

    _clear_prefix(_NUEVO)
    if rubro_id is None:
        st.session_state[_NUEVO_ABIERTO] = True
        return
    if any(
        r["id"] == rubro_id and r.get("activo", True)
        for r in st.session_state.get(_RUBROS_ACTIVOS, [])
    ):
        st.session_state[f"{_NUEVO}rubro"] = rubro_id  # only an option of the form
    st.session_state[_NUEVO_ABIERTO] = rubro_id
    _abrir(f"r{rubro_id}")


def _abierta(clave: str) -> bool:
    return clave in st.session_state.get(_ABIERTOS, set())


def _abrir(*claves: str) -> None:
    st.session_state.setdefault(_ABIERTOS, set()).update(claves)


def _alternar(
    clave: str, items: tuple[int, ...] = (), gastos: tuple[int, ...] = (), rubro=None
) -> None:
    """Open or close a row. Closing cancels the forms open inside it: their
    widgets stop being drawn, Streamlit forgets their values, and reopening
    must not bring back a half-reset draft (e.g. a gasto in the wrong currency).
    """

    abiertos = st.session_state.setdefault(_ABIERTOS, set())
    if clave not in abiertos:
        abiertos.add(clave)
        return
    abiertos.discard(clave)
    if st.session_state.get(_GASTO_ABIERTO) in items:
        _clear_prefix(_gasto_prefijo(st.session_state.pop(_GASTO_ABIERTO)))
    if st.session_state.get(_EDITANDO) in items:
        _clear_prefix(_editar_prefijo(st.session_state.pop(_EDITANDO)))
    if st.session_state.get(_GASTO_TC) in gastos:
        st.session_state.pop(f"tc_gasto_{st.session_state.pop(_GASTO_TC)}", None)
    abierto = st.session_state.get(_NUEVO_ABIERTO)
    if rubro is not None and abierto is not True and abierto == rubro:
        st.session_state.pop(_NUEVO_ABIERTO, None)
        _clear_prefix(_NUEVO)


def _monto(valor, moneda: str) -> str:
    return "—" if valor is None else finanzas.formato_monto(valor, moneda)


def _icono(col, icono: str, key: str, ayuda: str, disabled: bool = False) -> bool:
    """A small icon button; ``ayuda`` is its accessible description and tooltip."""

    return col.button(icono, key=key, help=ayuda, type="tertiary", disabled=disabled)


def _celdas(cols, valores: list[str]) -> None:
    """Fill the value columns (all but the first and the last)."""

    for col, valor in zip(cols[1:-1], valores, strict=True):
        col.markdown(valor)


def _render_presupuesto(
    supabase,
    items: list[dict],
    gastos: list[dict],
    activos: list[dict],
    rubros: list[dict],
    rubros_por_id: dict,
    obra_id: int,
    moneda_vista: str,
) -> None:
    st.subheader("Presupuesto de la obra")
    vigentes = [i for i in items if not i.get("anulado")]
    st.session_state[_RUBROS_ACTIVOS] = activos

    if st.session_state.get(_NUEVO_ABIERTO) is True:  # «+ Agregar ítem», sin rubro
        _form_nuevo_item(supabase, obra_id, activos, vigentes)
    else:
        st.button("+ Agregar ítem", key="item_agregar", on_click=_abrir_alta, args=(None,))

    if not vigentes:
        st.caption("Todavía no hay ítems en el presupuesto de esta obra.")
        for clave in (_A_BORRAR, _GASTO_A_ANULAR):
            st.session_state.pop(clave, None)
        return

    orden = {r["id"]: (r.get("orden", 10**6), finanzas.normalizar(r["nombre"])) for r in rubros}
    grupos: dict[int, list[dict]] = {}
    for item in vigentes:
        grupos.setdefault(item["rubro_id"], []).append(item)
    gastos_por_item: dict[int, list[dict]] = {}
    for gasto in gastos:
        gastos_por_item.setdefault(gasto.get("presupuesto_item_id"), []).append(gasto)

    st.html(_CSS_TABLA)
    with st.container(key="tabla_presupuesto"):
        with st.container(key="tabla_cabecera"):
            for col, titulo in zip(st.columns(_ANCHOS), COLUMNAS, strict=True):
                col.markdown(f"**{titulo}**")
        for rubro_id in sorted(grupos, key=lambda r: orden.get(r, (10**6, ""))):
            del_rubro = grupos[rubro_id]
            de_sus_items = [g for i in del_rubro for g in gastos_por_item.get(i["id"], [])]
            _fila_rubro(
                supabase,
                rubro_id,
                del_rubro,
                de_sus_items,
                gastos_por_item,
                activos,
                rubros,
                rubros_por_id,
                obra_id,
                vigentes,
                moneda_vista,
            )

    _dialogos(supabase, vigentes, gastos, rubros_por_id)


def _fila_rubro(
    supabase,
    rubro_id: int,
    del_rubro: list[dict],
    gastos: list[dict],
    gastos_por_item: dict,
    activos: list[dict],
    rubros: list[dict],
    rubros_por_id: dict,
    obra_id: int,
    vigentes: list[dict],
    moneda: str,
) -> None:
    res = finanzas.calcular_resumen(del_rubro, gastos, rubros, moneda)
    fila = next((f for f in res.filas if f.rubro_id == rubro_id), None)
    presupuestado = fila.presupuestado if fila else res.presupuestado
    gastado = fila.gastado if fila else res.gastado
    nombre = _rubro_nombre(rubros_por_id, rubro_id)
    clave = f"r{rubro_id}"
    abierta = _abierta(clave)
    estado = finanzas.estado_con_icono(gastado, presupuestado)
    if res.incompleto:
        estado += f" · {len(res.sin_convertir)} sin cotización"

    with st.container(key=f"nivel_rubro_{rubro_id}"):
        cols = st.columns(_ANCHOS, vertical_alignment="center")
        flecha = "▾" if abierta else "▸"
        cols[0].button(
            f"{flecha} **{texto_seguro(nombre)}**",
            key=f"fila_rubro_{rubro_id}",
            type="tertiary",
            help=("Ocultar" if abierta else "Ver") + " los ítems de este rubro",
            on_click=_alternar,
            args=(clave,),
            kwargs={
                "items": tuple(i["id"] for i in del_rubro),
                "gastos": tuple(g["id"] for g in gastos),
                "rubro": rubro_id,
            },
        )
        _celdas(
            cols,
            [
                str(len(del_rubro)),
                _monto(presupuestado, moneda),
                _monto(gastado, moneda),
                _monto(gastado - presupuestado, moneda),
                finanzas.formato_porcentaje(fila.ejecutado if fila else None),
                estado,
            ],
        )
        # Callback: the new-item form may already be on screen (another rubro or the
        # top button), and its widgets can only be preset before they are drawn.
        activo = rubros_por_id.get(rubro_id, {}).get("activo", True)
        cols[-1].button(
            ":material/add:",
            key=f"rubro_agregar_{rubro_id}",
            # R7: a deactivated rubro keeps its items but takes no new ones.
            help=(
                f"Agregar un ítem en {texto_seguro(nombre)}"
                if activo
                else f"{texto_seguro(nombre)} está desactivado: no se le agregan ítems nuevos"
            ),
            type="tertiary",
            disabled=not activo,
            on_click=_abrir_alta,
            args=(rubro_id,),
        )

    abierto = st.session_state.get(_NUEVO_ABIERTO)
    if abierto is not True and abierto == rubro_id:  # True == 1: compare identity first
        _form_nuevo_item(supabase, obra_id, activos, vigentes)
    if not abierta:
        return
    for item in del_rubro:
        _fila_item(
            supabase,
            item,
            gastos_por_item.get(item["id"], []),
            activos,
            rubros,
            rubros_por_id,
            moneda,
        )


def _fila_item(
    supabase,
    item: dict,
    gastos: list[dict],
    activos: list[dict],
    rubros: list[dict],
    rubros_por_id: dict,
    moneda: str,
) -> None:
    item_id = item["id"]
    editando = st.session_state.get(_EDITANDO) == item_id
    cargando = st.session_state.get(_GASTO_ABIERTO) == item_id
    clave = f"i{item_id}"
    abierta = _abierta(clave)
    fila = finanzas.calcular_resumen([item], gastos, rubros, moneda).items[item_id]
    presupuestado = (
        None if fila.sin_convertir and item in fila.sin_convertir else fila.presupuestado
    )
    nombre = _item_nombre(item)
    original = (
        f"  \n:gray[Cargado: {texto_seguro(finanzas.formato_monto(item['monto'], item['moneda']))}]"
        if item["moneda"] != moneda
        else ""
    )
    estado = finanzas.estado_con_icono(fila.gastado, fila.presupuestado)
    if fila.sin_convertir:
        estado += " · total incompleto"

    with st.container(key=f"nivel_item_{item_id}"):
        cols = st.columns(_ANCHOS, vertical_alignment="center")
        flecha = "▾" if abierta else "▸"
        cols[0].button(
            f"{flecha} {texto_seguro(nombre)}",
            key=f"fila_item_{item_id}",
            type="tertiary",
            help=("Ocultar" if abierta else "Ver") + " los gastos de este ítem",
            on_click=_alternar,
            args=(clave,),
            kwargs={"gastos": tuple(g["id"] for g in gastos)},
        )
        _celdas(
            cols,
            [
                "",
                _monto(presupuestado, moneda) + original,
                _monto(fila.gastado, moneda),
                _monto(fila.gastado - fila.presupuestado, moneda),
                finanzas.formato_porcentaje(fila.ejecutado),
                estado,
            ],
        )
        acciones = cols[-1].container(horizontal=True, gap="small", key=f"acciones_i{item_id}")
        a1 = a2 = a3 = acciones
        if _icono(
            a1,
            ":material/add:",
            f"gasto_agregar_{item_id}",
            f"Registrar un gasto en {texto_seguro(nombre)}",
            disabled=cargando,
        ):
            prefijo = _gasto_prefijo(item_id)
            _clear_prefix(prefijo)  # vacío al abrir...
            st.session_state[f"{prefijo}moneda"] = item["moneda"]  # ...salvo la moneda (R15)
            st.session_state[_GASTO_ABIERTO] = item_id
            _abrir(clave)
            st.rerun()
        if _icono(
            a2,
            ":material/edit:",
            f"item_editar_{item_id}",
            f"Editar el ítem {texto_seguro(nombre)}",
        ):
            _clear_prefix(_editar_prefijo(item_id))  # arranca con los valores actuales
            st.session_state[_EDITANDO] = item_id
            st.rerun()
        if _icono(
            a3,
            ":material/delete:",
            f"item_borrar_{item_id}",
            f"Borrar el ítem {texto_seguro(nombre)}",
        ):
            st.session_state.pop(_GASTO_A_ANULAR, None)
            st.session_state[_A_BORRAR] = item_id
            st.rerun()

    if editando:
        _form_editar_item(supabase, item, activos, rubros_por_id)
    if cargando:
        _form_nuevo_gasto(supabase, item)
    if not abierta:
        return

    with st.container(key=f"nivel_gasto_detalle_{item_id}"):
        detalle = [
            f"Fecha de carga: {_fecha_txt(item.get('fecha') or '')}",
            f"Cotización: {_cotizacion_txt(item)}",
            f"Saldo: {_monto(fila.saldo, moneda)}",
        ]
        st.caption(texto_seguro(" · ".join(detalle)))
        if fila.sin_convertir:
            st.caption(
                f"⚠️ Total incompleto: {len(fila.sin_convertir)} registro(s) en otra moneda "
                "sin cotización. Cargala con el lápiz del gasto o del ítem."
            )
        if not fila.gastos:
            st.caption("Todavía no hay gastos en este ítem.")
    for gasto in sorted(fila.gastos, key=lambda x: (x.get("fecha") or "", x["id"]), reverse=True):
        _fila_gasto(supabase, gasto, moneda)


def _fila_gasto(supabase, g: dict, moneda: str) -> None:
    texto = f"{_fecha_txt(g['fecha'])} · {g['descripcion']}"
    if g.get("proveedor"):
        texto += f" · {g['proveedor']}"
    valor = finanzas.convertir(g["monto"], g["moneda"], g.get("tipo_cambio"), moneda)
    original = finanzas.formato_monto(g["monto"], g["moneda"])
    gastado = (
        original
        if g["moneda"] == moneda
        else f"{_monto(valor, moneda) if valor is not None else 'sin cotización'}  \n"
        f":gray[Cargado: {texto_seguro(original)}]"
    )
    anulado = bool(g.get("anulado"))

    with st.container(key=f"nivel_gasto_{g['id']}"):
        cols = st.columns(_ANCHOS, vertical_alignment="center")
        if anulado:
            cols[0].markdown(f"~~{texto_seguro(texto)}~~ — **Anulado**")
        else:
            cols[0].markdown(f"{texto_seguro(texto)}  \n:gray[{texto_seguro(_cotizacion_txt(g))}]")
        _celdas(cols, ["", "", f"~~{gastado}~~" if anulado else gastado, "", "", ""])
        if anulado:
            return
        acciones = cols[-1].container(horizontal=True, gap="small", key=f"acciones_g{g['id']}")
        a1 = a2 = acciones
        if _icono(
            a1,
            ":material/edit:",
            f"gasto_cotizacion_{g['id']}",
            "Corregir la cotización de este gasto",
        ):
            st.session_state.pop(f"tc_gasto_{g['id']}", None)
            st.session_state[_GASTO_TC] = g["id"]
            st.rerun()
        if _icono(a2, ":material/delete:", f"gasto_anular_{g['id']}", "Anular este gasto"):
            st.session_state.pop(_A_BORRAR, None)
            st.session_state[_GASTO_A_ANULAR] = g["id"]
            st.rerun()
    if st.session_state.get(_GASTO_TC) == g["id"]:
        _form_cotizacion_gasto(supabase, g)


def _dialogos(supabase, vigentes: list[dict], gastos: list[dict], rubros_por_id: dict) -> None:
    """At most one confirmation dialog per run (Streamlit shows one at a time)."""

    pendiente = st.session_state.get(_A_BORRAR)
    if pendiente is not None:
        item = next((i for i in vigentes if i["id"] == pendiente), None)
        if item is None:
            st.session_state.pop(_A_BORRAR, None)
        else:
            del_item = [g for g in gastos if g.get("presupuesto_item_id") == item["id"]]
            _dialogo_borrar(supabase, item, del_item, rubros_por_id)
            return
    a_anular = st.session_state.get(_GASTO_A_ANULAR)
    if a_anular is not None:
        gasto = next((g for g in gastos if g["id"] == a_anular and not g.get("anulado")), None)
        if gasto is None:
            st.session_state.pop(_GASTO_A_ANULAR, None)
        else:
            item = next((i for i in vigentes if i["id"] == gasto.get("presupuesto_item_id")), {})
            _dialogo_anular_gasto(supabase, gasto, item)


def _form_cotizacion_gasto(supabase, gasto: dict) -> None:
    with st.form(f"form_tc_gasto_{gasto['id']}"):
        valor = st.number_input(
            "Nueva cotización del dólar (pesos por dólar)",
            min_value=0.0,
            max_value=_TC_MAX,
            value=None,
            step=1.0,
            format="%.2f",
            key=f"tc_gasto_{gasto['id']}",
        )
        b1, b2 = st.columns(2)
        guardar = b1.form_submit_button(
            "Guardar cotización",
            type="primary",
            width="stretch",
            key=f"gasto_tc_guardar_{gasto['id']}",
        )
        cancelar = b2.form_submit_button(
            "Cancelar", width="stretch", key=f"gasto_tc_cancelar_{gasto['id']}"
        )
    if cancelar:
        st.session_state.pop(_GASTO_TC, None)
        st.rerun()
    if not guardar:
        return
    if not valor:
        st.error("No se guardó la cotización: ingresá un valor mayor que cero.")
        return
    try:
        finanzas.set_tipo_cambio(supabase, "gastos", gasto["id"], valor)
    except finanzas.FinanzasError as exc:
        st.error(f"No se guardó la cotización: {texto_seguro(exc)}")
        return
    _flash("success", "✅ Cotización corregida a mano.")
    st.session_state.pop(_GASTO_TC, None)
    st.rerun()


def _form_nuevo_gasto(supabase, item: dict) -> None:
    item_id = item["id"]
    prefijo = _gasto_prefijo(item_id)
    with st.form(f"form_nuevo_gasto_{item_id}", border=True):
        st.markdown(f"**Nuevo gasto en «{texto_seguro(_item_nombre(item))}»**")
        fecha = st.date_input(
            "Fecha (obligatoria)",
            value=finanzas.hoy(),
            max_value=finanzas.hoy(),
            format="DD/MM/YYYY",
            key=f"{prefijo}fecha",
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
            key=f"{prefijo}monto",
        )
        moneda = c2.radio(
            "Moneda (obligatoria)",
            finanzas.MONEDAS,
            horizontal=True,
            key=f"{prefijo}moneda",
            help="Arranca en la moneda del ítem; podés cambiarla.",
        )
        descripcion = st.text_input(
            "Descripción (obligatoria)",
            max_chars=200,
            placeholder="Ej.: seña, primera entrega",
            key=f"{prefijo}descripcion",
        )
        proveedor = st.text_input("Proveedor", max_chars=120, key=f"{prefijo}proveedor")
        tc = st.number_input(
            "Cotización del dólar (opcional)",
            min_value=0.0,
            max_value=_TC_MAX,
            value=None,
            step=1.0,
            format="%.2f",
            placeholder="Automática: MEP de la fecha",
            key=f"{prefijo}tc",
            help="Dejala vacía para usar el dólar MEP promedio de la fecha del gasto.",
        )
        b1, b2 = st.columns(2)
        guardar = b1.form_submit_button(
            "Guardar gasto", type="primary", width="stretch", key=f"gasto_guardar_{item_id}"
        )
        cancelar = b2.form_submit_button(
            "Cancelar", width="stretch", key=f"gasto_cancelar_{item_id}"
        )

    if cancelar:
        st.session_state.pop(_GASTO_ABIERTO, None)
        _clear_prefix(prefijo)
        st.rerun()
    if not guardar:
        return
    faltan = []
    if not monto:
        faltan.append("ingresá un monto mayor que cero")
    if not moneda:
        faltan.append("elegí la moneda")
    if not (descripcion or "").strip():
        faltan.append("escribí una descripción")
    if faltan:
        st.error("No se agregó el gasto: " + ", ".join(faltan) + ".")
        return
    try:
        gasto, aviso = finanzas.add_gasto(
            supabase,
            item_id,
            monto=monto,
            moneda=moneda,
            descripcion=descripcion,
            fecha=fecha,
            proveedor=proveedor,
            tipo_cambio=tc or None,
        )
    except finanzas.FinanzasError as exc:
        st.error(f"No se agregó el gasto: {texto_seguro(exc)}")
        return
    _flash(
        "success",
        "✅ Gasto registrado en "
        + texto_seguro(
            f"«{_item_nombre(item)}»: {finanzas.formato_monto(gasto['monto'], gasto['moneda'])}"
            f" · {_cotizacion_txt(gasto)}."
        ),
    )
    if aviso:
        _flash("warning", f"⚠️ {texto_seguro(aviso)}")
    st.session_state.pop(_GASTO_ABIERTO, None)
    _clear_prefix(prefijo)
    st.rerun()


def _faltantes(rubro_id, moneda) -> list[str]:
    faltan = []
    if rubro_id is None:
        faltan.append("elegí un rubro")
    if not moneda:
        faltan.append("elegí la moneda")
    return faltan


def _form_nuevo_item(supabase, obra_id: int, activos: list[dict], vigentes: list[dict]) -> None:
    sin_imprevistos = finanzas.imprevistos_vigente(vigentes) is None
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
            "Monto",
            min_value=0.0,
            max_value=_MONTO_MAX,
            value=None,
            step=1000.0,
            format="%.2f",
            placeholder="0,00",
            key=f"{_NUEVO}monto",
            help="Podés dejarlo vacío (queda en 0) y cargarlo después con «Editar ítem».",
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
        es_imprevistos = False
        if sin_imprevistos:
            es_imprevistos = st.checkbox(
                "Es el ítem de imprevistos",
                key=f"{_NUEVO}imprevistos",
                help="Ahí van los gastos que no corresponden a otro ítem.",
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
    faltan = _faltantes(rubro_id, moneda)
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
            descripcion=descripcion or (finanzas.IMPREVISTOS if es_imprevistos else None),
            tipo_cambio=tc or None,
            es_imprevistos=es_imprevistos,
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
    _abrir(f"r{item['rubro_id']}")  # que se vea el ítem nuevo
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
            "Monto",
            min_value=0.0,
            max_value=_MONTO_MAX,
            value=float(item["monto"]),
            step=1000.0,
            format="%.2f",
            key=f"{prefijo}monto",
            help="Puede ser 0 si todavía no tiene precio.",
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
    faltan = _faltantes(rubro_id, moneda)
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


def _dialogo_borrar(supabase, item: dict, gastos: list[dict], rubros_por_id: dict) -> None:
    """R10 / #35 R12b: confirm in a dialog that names the item and warns about its
    gastos; «Borrar» hides the item and its gastos and keeps them in the database."""

    vigentes = [g for g in gastos if not g.get("anulado")]

    @st.dialog("¿Borrar este ítem del presupuesto?", on_dismiss=_cancelar_borrado)
    def dialogo() -> None:
        rubro = _rubro_nombre(rubros_por_id, item["rubro_id"])
        st.markdown(
            f"Vas a borrar **{texto_seguro(_item_nombre(item))}** "
            f"de **{texto_seguro(rubro)}** por "
            f"**{texto_seguro(finanzas.formato_monto(item['monto'], item['moneda']))}**."
        )
        if vigentes:
            totales = finanzas.calcular_resumen([item], vigentes, [], item["moneda"])
            monto = finanzas.formato_monto(totales.gastado, item["moneda"])
            incompleto = " (más gastos sin cotización)" if totales.incompleto else ""
            st.warning(
                f"⚠️ Este ítem tiene {len(vigentes)} gasto(s) asociado(s) por "
                f"{texto_seguro(monto)}{incompleto}. Si lo borrás, también se borran sus "
                "gastos y dejan de sumar en el presupuesto."
            )
        st.markdown(
            "Deja de sumar en el presupuesto y en los totales. Queda guardado en el "
            "historial de la obra."
        )
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key="item_borrar_cancelar", width="stretch"):
            _cancelar_borrado()
            st.rerun()
        etiqueta = "Borrar ítem y gastos" if vigentes else "Borrar ítem"
        if c2.button(etiqueta, key="item_borrar_confirmar", type="primary", width="stretch"):
            try:
                finanzas.borrar_presupuesto_item(supabase, item["id"])
            except finanzas.FinanzasError as exc:
                st.error(f"No se borró el ítem: {texto_seguro(exc)}")
                return
            for clave in (_EDITANDO, _GASTO_ABIERTO):
                if st.session_state.get(clave) == item["id"]:
                    st.session_state.pop(clave, None)
            _cancelar_borrado()
            _flash(
                "success",
                "✅ Ítem borrado del presupuesto"
                + (f", con sus {len(vigentes)} gasto(s)." if vigentes else "."),
            )
            st.rerun()

    dialogo()


def _cancelar_anulacion() -> None:
    st.session_state.pop(_GASTO_A_ANULAR, None)


def _dialogo_anular_gasto(supabase, gasto: dict, item: dict) -> None:
    """#35 R14: same confirmation pattern as deleting an item."""

    @st.dialog("¿Anular este gasto?", on_dismiss=_cancelar_anulacion)
    def dialogo() -> None:
        st.markdown(
            f"Vas a anular **{texto_seguro(gasto['descripcion'])}** del "
            f"{texto_seguro(_fecha_txt(gasto['fecha']))} por "
            f"**{texto_seguro(finanzas.formato_monto(gasto['monto'], gasto['moneda']))}**"
            f" en **{texto_seguro(_item_nombre(item))}**."
        )
        st.markdown("Deja de sumar, pero se sigue viendo tachado y queda guardado.")
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key="gasto_anular_cancelar", width="stretch"):
            _cancelar_anulacion()
            st.rerun()
        if c2.button("Anular gasto", key="gasto_anular_confirmar", type="primary", width="stretch"):
            try:
                finanzas.anular_gasto(supabase, gasto["id"])
            except finanzas.FinanzasError as exc:
                st.error(f"No se anuló el gasto: {texto_seguro(exc)}")
                return
            _cancelar_anulacion()
            _flash("success", "✅ Gasto anulado.")
            st.rerun()

    dialogo()
