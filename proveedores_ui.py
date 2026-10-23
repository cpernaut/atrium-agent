"""🏢 Proveedores (F-06, #37): the team's shared list. Data lives in ``atrium.proveedores``.

- List with search, rubro filter and «Mostrar eliminados».
- Ficha: contact buttons, purchases in every obra and star ratings (one per socio).
- Alta, edición and «Eliminar» (archives, with confirmation; can be restored).
- ``alta_rapida``: the short form used from the gasto forms.

Accessibility: every input has a visible label, required fields say so, stars
always come with their number, user text is escaped before rendering.
"""

from __future__ import annotations

import streamlit as st

from atrium import finanzas, proveedores
from ui_utils import texto_seguro

_AVISOS = "prov_avisos"
_ABIERTO = "prov_abierto"  # id of the proveedor whose ficha is open
_EDITANDO = "prov_editando"  # id being edited
_NUEVO = "prov_nuevo"  # the «+ Nuevo proveedor» form is open
_A_ELIMINAR = "prov_a_eliminar"  # id waiting for confirmation
_CAMPOS = ("nombre", "contacto", "telefono", "email", "web", "cuit", "zona", "notas", "rubro_ids")


def _aviso(tipo: str, mensaje: str) -> None:
    st.session_state.setdefault(_AVISOS, []).append((tipo, mensaje))


def _limpiar(prefijo: str) -> None:
    for clave in [k for k in st.session_state if str(k).startswith(prefijo)]:
        st.session_state.pop(clave, None)


def _rubros(supabase) -> tuple[dict[int, str], list[int]]:
    """({id: nombre} of every rubro, [ids of active rubros in order])."""

    todos = finanzas.list_rubros(supabase, incluir_inactivos=True)
    return {r["id"]: r["nombre"] for r in todos}, [r["id"] for r in todos if r.get("activo", True)]


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
def render_proveedores_page(supabase, user) -> None:
    st.header("Proveedores")
    for tipo, mensaje in st.session_state.pop(_AVISOS, []):
        getattr(st, tipo)(mensaje)
    try:
        lista = proveedores.list_proveedores(supabase, incluir_archivados=True)
        nombres_rubros, activos = _rubros(supabase)
        calificaciones = proveedores.list_calificaciones(supabase)
    except (proveedores.ProveedoresError, finanzas.FinanzasError) as exc:
        st.error(f"No se pudieron leer los proveedores: {texto_seguro(exc)}")
        st.caption("¿Ya corriste el `supabase_schema.sql` actualizado en Supabase?")
        return

    abierto = next((p for p in lista if p["id"] == st.session_state.get(_ABIERTO)), None)
    if abierto is not None:
        _dialogo_eliminar(supabase, lista)
        _render_ficha(supabase, user, abierto, nombres_rubros, activos, calificaciones)
        return
    st.session_state.pop(_ABIERTO, None)
    _dialogo_eliminar(supabase, lista)
    _render_lista(supabase, lista, nombres_rubros, activos, calificaciones)


def _render_lista(supabase, lista, nombres_rubros, activos, calificaciones) -> None:
    c1, c2 = st.columns([3, 2])
    texto = c1.text_input(
        "Buscar", placeholder="Nombre, contacto, teléfono, rubro…", key="prov_buscar"
    )
    rubro = c2.selectbox(
        "Rubro",
        [None, *activos],
        format_func=lambda r: "Todos los rubros" if r is None else nombres_rubros[r],
        key="prov_rubro",
    )
    c1, c2 = st.columns([1, 1], vertical_alignment="center")
    if c1.button("+ Nuevo proveedor", key="prov_nuevo_abrir", type="primary"):
        st.session_state[_NUEVO] = True
        _limpiar("prov_form_nuevo_")
        st.rerun()
    mostrar_eliminados = c2.checkbox("Mostrar eliminados", key="prov_mostrar_eliminados")

    if st.session_state.get(_NUEVO):
        _form_proveedor(supabase, None, nombres_rubros, activos)

    visibles = [p for p in lista if mostrar_eliminados or not p.get("archivado")]
    filtrados = proveedores.filtrar(visibles, texto, rubro, nombres_rubros)
    if not lista:
        st.info("Todavía no hay proveedores. Cargá el primero con «+ Nuevo proveedor».")
        return
    if not filtrados:
        st.caption("Ningún proveedor coincide con la búsqueda.")
        return
    promedios = proveedores.promedios(calificaciones)
    try:
        compras = proveedores.resumen_compras(supabase)
    except proveedores.ProveedoresError:
        compras = {}
    for p in filtrados:
        _tarjeta(p, nombres_rubros, promedios.get(p["id"], (None, 0)), compras.get(p["id"]))


def _tarjeta(p: dict, nombres_rubros: dict, promedio: tuple, compras) -> None:
    with st.container(border=True, key=f"prov_tarjeta_{p['id']}"):
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        titulo = f"**{texto_seguro(p['nombre'])}**"
        if p.get("archivado"):
            titulo = f"~~{texto_seguro(p['nombre'])}~~ · **Eliminado**"
        estrellas = proveedores.estrellas_txt(*promedio) if promedio[0] is not None else ""
        c1.markdown(titulo + (f" · {texto_seguro(estrellas)}" if estrellas else ""))
        rubros = [nombres_rubros[r] for r in p.get("rubro_ids") or [] if r in nombres_rubros]
        datos = [", ".join(rubros), p.get("contacto"), p.get("telefono"), p.get("email")]
        detalle = " · ".join(texto_seguro(d) for d in datos if d)
        if detalle:
            c1.caption(detalle)
        if compras is not None and compras.cantidad:
            obras = len(compras.obras)
            c1.caption(
                texto_seguro(
                    f"{compras.cantidad} gasto{'s' if compras.cantidad != 1 else ''} en "
                    f"{obras} obra{'s' if obras != 1 else ''} · {compras.total_txt()}"
                )
            )
        if c2.button("Abrir", key=f"prov_abrir_{p['id']}", width="stretch"):
            st.session_state[_ABIERTO] = p["id"]
            st.session_state.pop(_EDITANDO, None)
            st.rerun()


# --------------------------------------------------------------------------- #
# Ficha
# --------------------------------------------------------------------------- #
def _render_ficha(supabase, user, p, nombres_rubros, activos, calificaciones) -> None:
    pid = p["id"]
    if st.button("← Volver a la lista", key="prov_volver", type="tertiary"):
        st.session_state.pop(_ABIERTO, None)
        st.session_state.pop(_EDITANDO, None)
        st.rerun()

    titulo = texto_seguro(p["nombre"])
    st.subheader(f"{titulo} · Eliminado" if p.get("archivado") else titulo)
    propias = [c for c in calificaciones if c["proveedor_id"] == pid]
    st.markdown(texto_seguro(proveedores.estrellas_txt(*proveedores.promedio(propias))))

    acciones = st.container(horizontal=True, gap="small", key=f"prov_acciones_{pid}")
    if acciones.button("✏️ Editar", key=f"prov_editar_{pid}"):
        st.session_state[_EDITANDO] = pid
        _limpiar(f"prov_form_{pid}_")
        st.rerun()
    if p.get("archivado"):
        if acciones.button("Restaurar", key=f"prov_restaurar_{pid}"):
            try:
                proveedores.set_archivado(supabase, pid, False)
            except proveedores.ProveedoresError as exc:
                st.error(texto_seguro(exc))
                return
            _aviso("success", f"Proveedor «{texto_seguro(p['nombre'])}» restaurado.")
            st.rerun()
    elif acciones.button("🗑️ Eliminar", key=f"prov_eliminar_{pid}"):
        st.session_state[_A_ELIMINAR] = pid
        st.rerun()

    if st.session_state.get(_EDITANDO) == pid:
        _form_proveedor(supabase, p, nombres_rubros, activos)
        return

    rubros = [nombres_rubros[r] for r in p.get("rubro_ids") or [] if r in nombres_rubros]
    filas = [
        ("Rubros", ", ".join(rubros)),
        ("Contacto", p.get("contacto")),
        ("Teléfono", p.get("telefono")),
        ("Mail", p.get("email")),
        ("Web", p.get("web")),
        ("CUIT", p.get("cuit")),
        ("Zona", p.get("zona")),
        ("Notas", p.get("notas")),
    ]
    st.markdown(
        "  \n".join(f"**{e}:** {texto_seguro(v)}" for e, v in filas if v)
        or "Sin datos de contacto."
    )
    enlaces = proveedores.enlaces_contacto(p)
    if enlaces:
        botones = st.container(horizontal=True, gap="small", key=f"prov_contacto_{pid}")
        for etiqueta, url in enlaces:
            botones.link_button(etiqueta, url)

    st.divider()
    _render_compras(supabase, pid)
    st.divider()
    _render_calificaciones(supabase, user, p, propias)


def _render_compras(supabase, pid: int) -> None:
    st.markdown("**Compras**")
    try:
        compras = proveedores.compras(supabase, pid)
    except proveedores.ProveedoresError as exc:
        st.error(f"No se pudieron leer las compras: {texto_seguro(exc)}")
        return
    if not compras.cantidad:
        st.caption("Todavía no hay gastos con este proveedor.")
        return
    st.markdown(f"Total: {texto_seguro(compras.total_txt())}")
    for obra in compras.obras:
        totales = " · ".join(finanzas.formato_monto(v, m) for m, v in sorted(obra.totales.items()))
        n = len(obra.gastos)
        with st.expander(f"{obra.obra} · {n} gasto{'s' if n != 1 else ''} · {totales}"):
            for g in obra.gastos:
                fecha = str(g.get("fecha") or "")[:10]
                if len(fecha) == 10:
                    fecha = f"{fecha[8:10]}/{fecha[5:7]}/{fecha[:4]}"
                st.markdown(
                    texto_seguro(
                        f"{fecha} · {g['descripcion']} · "
                        f"{finanzas.formato_monto(g['monto'], g['moneda'])}"
                    )
                )


def _render_calificaciones(supabase, user, p: dict, propias: list[dict]) -> None:
    pid = p["id"]
    st.markdown("**Calificaciones**")
    mia = next((c for c in propias if c.get("creado_por") == user.id), None)
    if not p.get("archivado") or mia:
        prefijo = f"prov_calif_{pid}_"
        st.session_state.setdefault(f"{prefijo}estrellas", int(mia["estrellas"]) if mia else None)
        st.session_state.setdefault(f"{prefijo}comentario", (mia or {}).get("comentario") or "")
        with st.form(f"form_calificacion_{pid}"):
            estrellas = st.radio(
                "Tu calificación (obligatoria)",
                [1, 2, 3, 4, 5],
                format_func=lambda n: f"{'★' * n} {n}",
                horizontal=True,
                key=f"{prefijo}estrellas",
            )
            comentario = st.text_input(
                "Comentario",
                max_chars=500,
                key=f"{prefijo}comentario",
                placeholder="Ej.: cumple plazos, buen precio",
            )
            guardar = st.form_submit_button(
                "Guardar calificación" if not mia else "Cambiar mi calificación"
            )
        if guardar:
            try:
                proveedores.calificar(
                    supabase, pid, user.id, estrellas, comentario, autor=user.email
                )
            except proveedores.ProveedoresError as exc:
                st.error(f"No se guardó la calificación: {texto_seguro(exc)}")
                return
            _limpiar(prefijo)
            _aviso("success", "✅ Calificación guardada.")
            st.rerun()
    if not propias:
        st.caption("Todavía nadie lo calificó.")
    for c in propias:
        fecha = str(c.get("editado_en") or c.get("created_at") or "")[:10]
        if len(fecha) == 10 and fecha[4] == "-":
            fecha = f"{fecha[8:10]}/{fecha[5:7]}/{fecha[:4]}"
        partes = [proveedores.estrellas_txt(c["estrellas"]), c.get("autor") or "Un socio"]
        if c.get("comentario"):
            partes.append(f"«{c['comentario']}»")
        if fecha:
            partes.append(fecha)
        st.markdown(texto_seguro(" · ".join(partes)))


# --------------------------------------------------------------------------- #
# Alta y edición
# --------------------------------------------------------------------------- #
def _form_proveedor(supabase, p: dict | None, nombres_rubros: dict, activos: list[int]) -> None:
    """Full form: a new proveedor (``p`` None) or the edition of ``p``."""

    prefijo = "prov_form_nuevo_" if p is None else f"prov_form_{p['id']}_"
    actuales = [r for r in (p or {}).get("rubro_ids") or [] if r in nombres_rubros]
    opciones_rubros = activos + [r for r in actuales if r not in activos]
    if p is not None:
        for campo in _CAMPOS:
            st.session_state.setdefault(
                f"{prefijo}{campo}", actuales if campo == "rubro_ids" else p.get(campo) or ""
            )

    with st.form(f"{prefijo}form", border=True):
        st.markdown(
            "**Nuevo proveedor**" if p is None else f"**Editar «{texto_seguro(p['nombre'])}»**"
        )
        st.text_input("Nombre (obligatorio)", max_chars=120, key=f"{prefijo}nombre")
        st.multiselect(
            "Rubros que atiende",
            opciones_rubros,
            format_func=lambda r: nombres_rubros.get(r, f"Rubro #{r}"),
            key=f"{prefijo}rubro_ids",
            placeholder="Elegí uno o varios",
            help="Salen de la lista de 🏷️ Rubros, la misma del presupuesto.",
        )
        c1, c2 = st.columns(2)
        c1.text_input("Persona de contacto", max_chars=120, key=f"{prefijo}contacto")
        c2.text_input(
            "Teléfono",
            max_chars=30,
            key=f"{prefijo}telefono",
            placeholder="221 555 1234",
            help="Con característica, sin 0 ni 15: así funcionan Llamar y WhatsApp.",
        )
        c1, c2 = st.columns(2)
        c1.text_input("Mail", max_chars=120, key=f"{prefijo}email")
        c2.text_input("Web", max_chars=300, key=f"{prefijo}web", placeholder="https://…")
        c1, c2 = st.columns(2)
        c1.text_input("CUIT", max_chars=13, key=f"{prefijo}cuit", placeholder="30-71234567-1")
        c2.text_input("Zona o dirección", max_chars=120, key=f"{prefijo}zona")
        st.text_area("Notas", max_chars=1000, key=f"{prefijo}notas")
        b1, b2 = st.columns(2)
        guardar = b1.form_submit_button("Guardar proveedor", type="primary", width="stretch")
        cancelar = b2.form_submit_button("Cancelar", width="stretch")

    if cancelar:
        st.session_state.pop(_NUEVO if p is None else _EDITANDO, None)
        _limpiar(prefijo)
        st.rerun()
    if not guardar:
        return
    datos = {campo: st.session_state.get(f"{prefijo}{campo}") for campo in _CAMPOS}
    try:
        if p is None:
            guardado = proveedores.create_proveedor(supabase, datos)
        else:
            guardado = proveedores.update_proveedor(supabase, p["id"], datos)
    except proveedores.ProveedoresError as exc:
        st.error(f"No se guardó el proveedor: {texto_seguro(exc)}")  # keeps what was typed
        return
    _limpiar(prefijo)
    if p is None:
        st.session_state.pop(_NUEVO, None)
        st.session_state[_ABIERTO] = guardado.get("id")
        _aviso("success", f"✅ Proveedor «{texto_seguro(guardado['nombre'])}» agregado.")
    else:
        st.session_state.pop(_EDITANDO, None)
        _aviso("success", "✅ Proveedor actualizado.")
    st.rerun()


def _cancelar_eliminacion() -> None:
    st.session_state.pop(_A_ELIMINAR, None)


def _dialogo_eliminar(supabase, lista: list[dict]) -> None:
    pid = st.session_state.get(_A_ELIMINAR)
    if pid is None:
        return
    p = next((x for x in lista if x["id"] == pid and not x.get("archivado")), None)
    if p is None:
        _cancelar_eliminacion()
        return

    @st.dialog("¿Eliminar este proveedor?", on_dismiss=_cancelar_eliminacion)
    def dialogo() -> None:
        st.markdown(
            f"Vas a eliminar **{texto_seguro(p['nombre'])}**. Deja de aparecer en la lista "
            "y al cargar gastos, pero sus gastos anteriores lo siguen mostrando. Lo podés "
            "restaurar desde «Mostrar eliminados»."
        )
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key="prov_eliminar_cancelar", width="stretch"):
            _cancelar_eliminacion()
            st.rerun()
        if c2.button(
            "Eliminar proveedor", key="prov_eliminar_confirmar", type="primary", width="stretch"
        ):
            try:
                proveedores.set_archivado(supabase, p["id"], True)
            except proveedores.ProveedoresError as exc:
                st.error(f"No se eliminó: {texto_seguro(exc)}")
                return
            _cancelar_eliminacion()
            st.session_state.pop(_ABIERTO, None)
            _aviso("success", f"Proveedor «{texto_seguro(p['nombre'])}» eliminado.")
            st.rerun()

    dialogo()


# --------------------------------------------------------------------------- #
# Used from the gasto forms
# --------------------------------------------------------------------------- #
def selector_opciones(lista: list[dict], actual: int | None = None) -> list[int | None]:
    """Options for a gasto's proveedor: none, the active ones, and its current one."""

    opciones: list[int | None] = [None]
    opciones += [p["id"] for p in lista if not p.get("archivado")]
    if actual is not None and actual not in opciones:
        opciones.append(actual)
    return opciones


def nombre(lista: list[dict], proveedor_id: int | None) -> str:
    if proveedor_id is None:
        return "Sin proveedor"
    p = next((x for x in lista if x["id"] == proveedor_id), None)
    if p is None:
        return f"Proveedor #{proveedor_id}"
    return f"{p['nombre']} (eliminado)" if p.get("archivado") else p["nombre"]


def alta_rapida(supabase, clave_destino: str, prefijo: str, rubro_id: int | None = None) -> None:
    """«+ Nuevo proveedor» inside a gasto: name (required), phone and rubro.

    On save, the new proveedor becomes the value of the widget ``clave_destino``
    (it must be drawn after this form, in the same run or the next).
    """

    abierta = f"{prefijo}abierta"
    if not st.session_state.get(abierta):
        if st.button("+ Nuevo proveedor", key=f"{prefijo}abrir", type="tertiary"):
            st.session_state[abierta] = True
            st.rerun()
        return
    with st.form(f"{prefijo}form", border=True):
        st.markdown("**Nuevo proveedor** · después completás el resto en 🏢 Proveedores")
        nombre_nuevo = st.text_input("Nombre (obligatorio)", max_chars=120, key=f"{prefijo}nombre")
        telefono = st.text_input("Teléfono", max_chars=30, key=f"{prefijo}telefono")
        b1, b2 = st.columns(2)
        guardar = b1.form_submit_button("Agregar proveedor", type="primary", width="stretch")
        cancelar = b2.form_submit_button("Cancelar", width="stretch")
    if cancelar:
        _limpiar(prefijo)
        st.rerun()
    if not guardar:
        return
    datos = {"nombre": nombre_nuevo, "telefono": telefono}
    if rubro_id is not None:
        datos["rubro_ids"] = [rubro_id]
    try:
        nuevo = proveedores.create_proveedor(supabase, datos)
    except proveedores.ProveedoresError as exc:
        st.error(f"No se agregó el proveedor: {texto_seguro(exc)}")
        return
    _limpiar(prefijo)
    st.session_state[clave_destino] = nuevo["id"]
    st.rerun()
