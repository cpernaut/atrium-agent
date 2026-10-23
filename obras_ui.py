"""Streamlit screens for the obras tracker (#49). Data access lives in ``atrium.obras``.

- the obra activa: its picker (left menu) and the header that always shows it;
- 🏗️ Obra activa: Detalle (editable), Bitácora and Presupuesto;
- 📋 Obras: the list; ➕ Nueva obra: the form to add one.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

import navegacion
from atrium import finanzas, obras
from plata_ui import render_plata
from ui_utils import texto_seguro

_SCHEMA_HINT = (
    "¿Ya corriste `supabase_schema.sql` en el SQL Editor de Supabase? "
    "Ahí se crean las tablas `obras` y `bitacora`."
)


def load_obras(supabase) -> list[obras.Obra] | None:
    try:
        return obras.list_obras(supabase)
    except obras.ObrasError as exc:
        st.error(f"No se pudieron leer las obras: {texto_seguro(exc)}")
        st.caption(_SCHEMA_HINT)
        return None


# --------------------------------------------------------------------------- #
# Obra activa: one for the whole app (UX-02), remembered per user (#49 D9)
# --------------------------------------------------------------------------- #
OBRA_ELEGIDA = "obra_elegida"  # widget key: the obra every screen and the agent use
_ULTIMA = "obra_ultima"  # last obra the user chose (survives a missing widget)
_PENDIENTE = "obra_elegida_nueva"  # obra to activate on the next run (new or opened)
_GUARDADA = "obra_guardada"  # the obra activa last saved in the user's metadata
_AVISOS = "obras_avisos"  # messages to show after the rerun that follows a save


def _opcion(obra: obras.Obra) -> str:
    return f"{obra['nombre']} · {obra.get('estado') or 'Sin estado'}"


def activar_obra(obra_id: int) -> None:
    """Make ``obra_id`` the obra activa from the next run on.

    The picker is already drawn in this run, so its value can't change now.
    """

    st.session_state[_PENDIENTE] = obra_id


def select_obra(supabase, user, lista: list[obras.Obra]) -> int | None:
    """The obra activa picker, in the left menu.

    Default: the obra this user worked on last (saved in their account, so it
    holds across sessions and devices); else the newest En curso; never a
    Terminada or Cancelada one while there is an active obra.
    """

    if _ULTIMA not in st.session_state:
        guardada = obras.obra_activa_guardada(user)
        st.session_state[_ULTIMA] = guardada
        st.session_state[_GUARDADA] = guardada
    if not lista:
        return None
    ordenadas = obras.ordenar_para_elegir(lista)
    ids = [o["id"] for o in ordenadas]
    nombres = {o["id"]: _opcion(o) for o in ordenadas}

    pendiente = st.session_state.pop(_PENDIENTE, None)
    if pendiente in ids:
        st.session_state[OBRA_ELEGIDA] = pendiente
    elif st.session_state.get(OBRA_ELEGIDA) not in ids:
        st.session_state[OBRA_ELEGIDA] = obras.obra_por_defecto(
            lista, st.session_state.get(_ULTIMA)
        )
    elegida = st.selectbox(
        "Obra activa",
        ids,
        format_func=lambda i: nombres[i],
        key=OBRA_ELEGIDA,
        help="La que ves en todas las pantallas y sobre la que trabaja el agente.",
    )
    st.session_state[_ULTIMA] = elegida
    if elegida != st.session_state.get(_GUARDADA):
        try:
            obras.guardar_obra_activa(supabase, user, elegida)
        except obras.ObrasError:
            # Best-effort: the obra stays active in this session anyway.
            st.toast("⚠️ No se pudo recordar la obra activa para la próxima vez.")
        st.session_state[_GUARDADA] = elegida
    return elegida


_CSS_ENCABEZADO = """
<style>
/* The obra activa stays visible at the top while the page scrolls (#49).
   Sticky goes on Streamlit's wrapper: the container alone is as tall as its
   content, so it would have no room to stick. */
[data-testid="stLayoutWrapper"]:has(> .st-key-obra_encabezado) {
    position: sticky;
    top: 3.75rem;
    z-index: 990;
    background-color: #ffffff;
    border-bottom: 1px solid rgba(49, 51, 63, 0.15);
    padding: 0.6rem 0 !important;
    box-shadow: 0 6px 8px -8px rgba(0, 0, 0, 0.25);
}
.st-key-obra_encabezado p { margin: 0; }
/* Streamlit pulls the last paragraph up with a negative margin: undo it, or the
   text sticks out of the header. */
.st-key-obra_encabezado [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
/* Streamlit's top bar is see-through: make it solid so content scrolling
   under the header doesn't show above it. */
[data-testid="stHeader"] { background-color: #ffffff; }
/* With the menu open, the budget table (#45) needs the width: narrower side
   margins on computers (phones keep Streamlit's). */
@media (min-width: 800px) {
    [data-testid="stMainBlockContainer"] { padding-left: 2.5rem; padding-right: 2.5rem; }
}
</style>
"""


def render_encabezado(obra: obras.Obra | None) -> None:
    """The obra activa, always visible on top of every screen (#49)."""

    st.html(_CSS_ENCABEZADO)
    with st.container(key="obra_encabezado"):
        if obra is None:
            st.markdown("🏗️ **Sin obra activa** · cargá una en «Nueva obra»")
            return
        partes = [
            f"🏗️ **{texto_seguro(obra['nombre'])}**",
            texto_seguro(obra.get("estado") or "Sin estado"),
            f"{int(obra.get('avance') or 0)} % de avance",
        ]
        st.markdown(" · ".join(partes))


def mostrar_avisos() -> None:
    for tipo, mensaje in st.session_state.pop(_AVISOS, []):
        getattr(st, tipo)(mensaje)


def olvidar_formularios_de_obra() -> None:
    """Forget the Detalle widgets, so they show the obra's current data.

    Called when the data changed elsewhere (the agent updated avance or estado):
    otherwise Streamlit keeps the old widget values and saving the form would
    write them back over the new data.
    """

    for clave in [k for k in st.session_state if str(k).startswith(_PREFIJO_DETALLE)]:
        st.session_state.pop(clave, None)


# --------------------------------------------------------------------------- #
# 🏗️ Obra activa
# --------------------------------------------------------------------------- #
PESTANAS_OBRA = ["Detalle", "Bitácora", "Presupuesto"]


def render_obra_page(supabase, user, obra: obras.Obra | None, sin_obras: bool) -> None:
    if sin_obras:
        navegacion.ir_a(navegacion.NUEVA)  # #49 D8: with no obras, start by adding one
    if obra is None:
        st.info("Todavía no hay una obra activa. Cargá la primera en «➕ Nueva obra».")
        if st.button("➕ Nueva obra", key="ir_nueva_obra", type="primary"):
            navegacion.ir_a(navegacion.NUEVA)
        return
    tab_detalle, tab_bitacora, tab_presupuesto = st.tabs(PESTANAS_OBRA)
    with tab_detalle:
        _render_detalle(supabase, obra)
    with tab_bitacora:
        _render_bitacora(supabase, user, obra)
    with tab_presupuesto:
        render_plata(supabase, obra["id"])


_PREFIJO_DETALLE = "det_"


def _clave(campo: str, obra_id: int) -> str:
    return f"{_PREFIJO_DETALLE}{campo}_{obra_id}"


def _fecha(valor) -> date | None:
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _opciones(base: tuple[str, ...], actual: str | None) -> list[str]:
    """Picker options; a value saved before the list changed is kept, not lost."""

    return list(base) if not actual or actual in base else [*base, actual]


def _valores_obra(obra: obras.Obra) -> dict:
    """The form's values for ``obra``, as the widgets hold them."""

    return {
        "nombre": obra.get("nombre") or "",
        "cliente": obra.get("cliente") or "",
        "responsable": obra.get("responsable") or "",
        "direccion": obra.get("direccion") or "",
        "municipio": obra.get("municipio") or obras.MUNICIPIOS[0],
        "tipo": obra.get("tipo") or obras.TIPOS[0],
        "estado": obra.get("estado") if obra.get("estado") in obras.ESTADOS else obras.ESTADOS[0],
        "avance": int(obra.get("avance") or 0),
        "fecha_inicio": _fecha(obra.get("fecha_inicio")),
        "fecha_fin_estimada": _fecha(obra.get("fecha_fin_estimada")),
        "presupuesto": float(obra.get("presupuesto") or 0),
        "moneda": obra.get("moneda") if obra.get("moneda") in obras.MONEDAS else "ARS",
    }


def _a_guardar(valores: dict) -> dict:
    """Widget values -> database values (empty text and 0 budget are «no data»)."""

    datos = dict(valores)
    datos["nombre"] = str(valores["nombre"]).strip()
    for campo in ("cliente", "responsable", "direccion"):
        datos[campo] = str(valores[campo]).strip() or None
    for campo in ("fecha_inicio", "fecha_fin_estimada"):
        datos[campo] = valores[campo].isoformat() if valores[campo] else None
    datos["presupuesto"] = valores["presupuesto"] or None
    return datos


def cambios_obra(originales: dict, valores: dict) -> dict:
    """Only what the user changed in Detalle (so a save never rewrites the rest).

    ``originales`` are the values the form was filled with, not the obra as it
    is now: if someone else (or the agent) changed a field meanwhile, a save
    that didn't touch that field must not write the old value back (R4).
    """

    nuevos = _a_guardar(valores)
    antes = _a_guardar(originales)
    # A value the database holds as NULL and the form shows as a default (first
    # municipio, tipo) counts as unchanged unless the user picked something else.
    return {campo: v for campo, v in nuevos.items() if v != antes[campo]}


def _originales(obra_id: int) -> str:
    """Session key with the values the Detalle form was filled with."""

    return f"{_PREFIJO_DETALLE}_originales_{obra_id}"


def _render_detalle(supabase, obra: obras.Obra) -> None:
    obra_id = obra["id"]
    valores = _valores_obra(obra)
    # Fill the form (and remember what it was filled with) only when it is
    # fresh: while the user edits, their values stay even if the obra changes.
    claves = [_clave(campo, obra_id) for campo in valores]
    if _originales(obra_id) not in st.session_state or any(
        k not in st.session_state for k in claves
    ):
        for campo, valor in valores.items():
            st.session_state[_clave(campo, obra_id)] = valor
        st.session_state[_originales(obra_id)] = dict(valores)

    def clave(campo: str) -> str:
        return _clave(campo, obra_id)

    with st.form(f"detalle_obra_{obra_id}"):
        st.text_input("Nombre de la obra (obligatorio)", key=clave("nombre"))
        c1, c2 = st.columns(2)
        c1.text_input("Cliente", key=clave("cliente"))
        c2.text_input("Responsable", key=clave("responsable"))
        c1, c2 = st.columns([2, 1])
        c1.text_input("Dirección", key=clave("direccion"))
        c2.selectbox(
            "Municipio",
            _opciones(obras.MUNICIPIOS, obra.get("municipio")),
            key=clave("municipio"),
            help="Define qué código de edificación usa el agente.",
        )
        c1, c2 = st.columns(2)
        c1.selectbox("Tipo", _opciones(obras.TIPOS, obra.get("tipo")), key=clave("tipo"))
        c2.selectbox("Estado", obras.ESTADOS, key=clave("estado"))
        st.slider("Avance (%)", 0, 100, key=clave("avance"))
        c1, c2 = st.columns(2)
        c1.date_input("Fecha de inicio", format="DD/MM/YYYY", key=clave("fecha_inicio"))
        c2.date_input("Fin estimado", format="DD/MM/YYYY", key=clave("fecha_fin_estimada"))
        c1, c2 = st.columns([3, 1])
        c1.number_input(
            "Presupuesto de la obra",
            min_value=0.0,
            step=1000.0,
            key=clave("presupuesto"),
            help="Cambiarlo no recalcula el ítem «Imprevistos» del presupuesto.",
        )
        c2.selectbox("Moneda", obras.MONEDAS, key=clave("moneda"))
        c1, c2 = st.columns(2)
        guardar = c1.form_submit_button("Guardar cambios", type="primary")
        descartar = c2.form_submit_button("Descartar cambios")

    if descartar:
        olvidar_formularios_de_obra()
        st.rerun()
    if guardar:
        cambios = cambios_obra(
            st.session_state[_originales(obra_id)],
            {c: st.session_state[clave(c)] for c in valores},
        )
        if not cambios:
            st.info("No hay cambios para guardar.")
            return
        try:
            obras.update_obra(supabase, obra_id, cambios)
        except obras.ObrasError as exc:
            st.error(texto_seguro(exc))  # the form keeps what was typed
            return
        olvidar_formularios_de_obra()
        st.session_state[_AVISOS] = [("success", "Obra actualizada.")]
        st.rerun()


def _render_bitacora(supabase, user, obra: obras.Obra) -> None:
    obra_id = obra["id"]

    with st.form("nota_bitacora"):
        fecha = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY", key="nota_fecha")
        nota = st.text_area("Nota de obra (obligatorio)", key="nota_texto")
        agregar = st.form_submit_button("Agregar nota")
    if agregar:
        try:
            obras.add_nota(supabase, obra_id, nota, autor=user.email, fecha=fecha)
        except obras.ObrasError as exc:
            st.error(texto_seguro(exc))  # the form keeps what was typed
        else:
            st.session_state.pop("nota_texto", None)  # empty after saving
            st.rerun()

    try:
        notas = obras.list_bitacora(supabase, obra_id)
    except obras.ObrasError as exc:
        st.error(texto_seguro(exc))
        return
    if not notas:
        st.caption("Sin notas todavía. También podés pedirle al agente: «anotá en esta obra…».")
    for n in notas:
        autor = texto_seguro(n.get("autor") or "—")
        st.markdown(f"**{texto_seguro(n['fecha'])}** · {autor}  \n{texto_seguro(n['nota'])}")
        st.divider()


# --------------------------------------------------------------------------- #
# 📋 Obras
# --------------------------------------------------------------------------- #
def render_lista_page(lista: list[obras.Obra] | None, obra: obras.Obra | None) -> None:
    st.header("Obras")
    if lista is None:
        return
    if not lista:
        st.info("Todavía no hay obras. Cargá la primera en «➕ Nueva obra».")
        return

    df = pd.DataFrame(lista)
    c1, c2, c3 = st.columns(3)
    c1.metric("Obras", len(df))
    c2.metric("En curso", int((df["estado"] == "En curso").sum()))
    c3.metric("Avance promedio", f"{df['avance'].mean():.0f}%")

    filtro = st.multiselect(
        "Filtrar por estado", obras.ESTADOS, key="lista_filtro", placeholder="Todos los estados"
    )
    activa = obra["id"] if obra else None
    mostradas = [o for o in obras.ordenar_para_elegir(lista) if not filtro or o["estado"] in filtro]
    if not mostradas:
        st.caption("Ninguna obra en ese estado.")
    for o in mostradas:
        _tarjeta_obra(o, o["id"] == activa)


def _tarjeta_obra(o: obras.Obra, es_activa: bool) -> None:
    with st.container(border=True, key=f"tarjeta_obra_{o['id']}"):
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        titulo = f"**{texto_seguro(o['nombre'])}**"
        if es_activa:
            titulo += " · :blue-badge[Obra activa]"
        avance = int(o.get("avance") or 0)
        c1.markdown(f"{titulo}  \n{texto_seguro(o.get('estado') or 'Sin estado')} · {avance} %")
        datos = [o.get("cliente"), o.get("municipio"), o.get("responsable")]
        if o.get("presupuesto") is not None:
            datos.append(finanzas.formato_monto(o["presupuesto"], o.get("moneda") or "ARS"))
        detalle = " · ".join(texto_seguro(d) for d in datos if d)
        if detalle:
            c1.caption(detalle)
        if c2.button(
            "Abrir",
            key=f"abrir_obra_{o['id']}",
            type="primary" if es_activa else "secondary",
            help="La deja como obra activa y muestra su detalle, bitácora y presupuesto.",
            width="stretch",
        ):
            activar_obra(o["id"])
            navegacion.ir_a(navegacion.OBRA)


# --------------------------------------------------------------------------- #
# ➕ Nueva obra
# --------------------------------------------------------------------------- #
def render_nueva_page(supabase, sin_obras: bool) -> None:
    st.header("Nueva obra")
    if sin_obras:
        st.info(
            "¡Te damos la bienvenida a Atrium Studio! Cargá la primera obra: después vas a poder "
            "llevar su bitácora, su presupuesto y sus gastos, y consultarle al agente."
        )
    with st.form("nueva_obra", clear_on_submit=True):
        nombre = st.text_input("Nombre de la obra (obligatorio)", key="nueva_nombre")
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

        if st.form_submit_button("Crear obra", type="primary"):
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
                avisos = [
                    ("success", f"Obra «{texto_seguro(nombre.strip())}» creada: es la obra activa.")
                ]
                avisos += _crear_imprevistos(supabase, creada)
                st.session_state[_AVISOS] = avisos
                if creada.get("id") is not None:
                    activar_obra(creada["id"])
                navegacion.ir_a(navegacion.OBRA)


def _crear_imprevistos(supabase, obra: obras.Obra) -> list[tuple[str, str]]:
    """#35 R12: every new obra starts with its «Imprevistos» budget item.

    Returns the messages to show after the rerun.
    """

    try:
        item, aviso = finanzas.crear_imprevistos(supabase, obra)
    except finanzas.FinanzasError as exc:
        return [
            (
                "warning",
                "⚠️ No se pudo crear el ítem «Imprevistos» del presupuesto: "
                f"{texto_seguro(exc)}. Podés agregarlo desde «+ Agregar ítem».",
            )
        ]
    avisos = [
        (
            "caption",
            "Presupuesto: se agregó el ítem «Imprevistos» por "
            f"{texto_seguro(finanzas.formato_monto(item['monto'], item['moneda']))} (10 % del "
            "presupuesto de la obra). Lo podés editar o borrar en la pestaña «Presupuesto».",
        )
    ]
    if aviso:
        avisos.append(("caption", f"⚠️ {texto_seguro(aviso)}"))
    return avisos
