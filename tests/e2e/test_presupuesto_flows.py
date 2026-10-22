"""F-03 · Presupuesto: lista por rubro, detalle, alta, edición y borrado (issue #9).

One test per acceptance criterion F-03-CA-14..25 (see the ficha and
docs/casos-e2e.md). Runs the real app with simulated services (conftest.py).
"""

from decimal import Decimal

import pytest

from atrium import finanzas, obras
from tests.e2e.conftest import click, texts

PLATA = 3  # «💰 Plata» tab inside 📋 Obras


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _obra(e2e):
    return obras.create_obra(e2e.db, {"nombre": "Casa Lote 12", "municipio": "La Plata"})


def _rubro(e2e, nombre):
    return finanzas.find_rubros(e2e.db, nombre)[0]["id"]


def _item(e2e, rubro, monto, moneda="ARS", descripcion=None):
    item, _ = finanzas.add_presupuesto_item(
        e2e.db, 1, monto=monto, moneda=moneda, rubro_id=_rubro(e2e, rubro), descripcion=descripcion
    )
    return item


def _plata(e2e):
    at = e2e.go_to_obras(e2e.login())
    return at.selectbox(key="plata_obra").set_value(1).run()


def _tab(at):
    return at.tabs[PLATA]


def _markdown(at) -> str:
    return "\n".join(m.value for m in _tab(at).markdown)


def _grupos(at) -> list[str]:
    """Group headers of the budget list, as the user reads them."""

    return [
        m.replace("\\", "").split(" · Gastado")[0]
        for m in (x.value for x in _tab(at).markdown)
        if "· Subtotal" in m
    ]


def _expanders(at) -> list[str]:
    """Item titles up to the total (gastado and estado are checked in test_plata_flows)."""

    return [
        e.label.replace("\\", "").split(" · ")[0] for e in _tab(at).expander if " — " in e.label
    ]


def _vigentes(e2e):
    return [i for i in finanzas.list_presupuesto(e2e.db, 1) if not i["anulado"]]


def _abrir_nuevo(at):
    return click(at, "+ Agregar ítem")


def _abrir_edicion(at, item_id):
    return at.button(key=f"item_editar_{item_id}").click().run()


def _pedir_borrado(at, item_id):
    return at.button(key=f"item_borrar_{item_id}").click().run()


# --------------------------------------------------------------------------- #
# Lista y detalle
# --------------------------------------------------------------------------- #
def test_f03_ca_14_lista_agrupada_por_rubro_con_subtotales(e2e):
    """F-03-CA-14: ítems en tres rubros -> grupos en orden de obra, con cantidad
    de ítems y subtotal."""

    _obra(e2e)
    _item(e2e, "Pintura", 800_000, descripcion="Látex interior")
    _item(e2e, "Fundaciones", 1_500_000, descripcion="Excavación")
    _item(e2e, "Fundaciones", 500_000, descripcion="Hormigón de limpieza")
    _item(e2e, "Estructura", 5_000_000, descripcion="Hierro y hormigón")

    at = _plata(e2e)

    assert not at.exception
    assert _grupos(at) == [
        "**Fundaciones** · 2 ítems · Subtotal ARS 2.000.000",
        "**Estructura** · 1 ítem · Subtotal ARS 5.000.000",
        "**Pintura** · 1 ítem · Subtotal ARS 800.000",
    ]
    assert _expanders(at)[:4] == [
        "Excavación — ARS 1.500.000",
        "Hormigón de limpieza — ARS 500.000",
        "Hierro y hormigón — ARS 5.000.000",
        "Látex interior — ARS 800.000",
    ]


def test_f03_ca_14b_subtotales_en_la_moneda_de_vista(e2e):
    """F-03-CA-14: los subtotales siguen la moneda elegida (USD con el MEP del ítem)."""

    _obra(e2e)
    _item(e2e, "Honorarios", 1000, moneda="USD", descripcion="Proyecto")
    _item(e2e, "Honorarios", 1_200_000, descripcion="Trámites")
    at = _plata(e2e).radio(key="plata_moneda").set_value("USD").run()

    assert _grupos(at) == ["**Honorarios y trámites** · 2 ítems · Subtotal USD 2.000"]


def test_f03_ca_15_detalle_del_item(e2e):
    """F-03-CA-15: el detalle muestra rubro, descripción, monto, moneda, fecha de
    carga y cotización con su origen, y las acciones Editar y Borrar."""

    _obra(e2e)
    item = _item(e2e, "Estructura", 3_200_000, descripcion="Hierro del 8")
    at = _plata(e2e)

    detalle = _markdown(at).replace("\\", "")
    hoy = finanzas.hoy()
    for linea in (
        "- **Rubro:** Estructura",
        "- **Descripción:** Hierro del 8",
        f"- **Fecha de carga:** {hoy:%d/%m/%Y}",
        "- **Cotización:** MEP 1.200,00 (automática)",
    ):
        assert linea in detalle, linea
    assert "**Total:** ARS 3.200.000" in detalle
    assert at.button(key=f"item_editar_{item['id']}").label == "Editar ítem"
    assert at.button(key=f"item_borrar_{item['id']}").label == "Borrar ítem"


def test_f03_ca_15b_sin_items(e2e):
    """F-03-CA-15: sin ítems, la sección lo dice y ofrece agregar."""

    _obra(e2e)
    at = _plata(e2e)
    assert "Todavía no hay ítems en el presupuesto de esta obra." in texts(at)
    assert any(b.label == "+ Agregar ítem" for b in at.button)


# --------------------------------------------------------------------------- #
# Alta
# --------------------------------------------------------------------------- #
def _campos_nuevo(at):
    return {
        "rubro": at.selectbox(key="nuevo_item_rubro").value,
        "descripcion": at.text_input(key="nuevo_item_descripcion").value,
        "monto": at.number_input(key="nuevo_item_monto").value,
        "moneda": at.radio(key="nuevo_item_moneda").value,
        "tc": at.number_input(key="nuevo_item_tc").value,
    }


VACIO = {"rubro": None, "descripcion": "", "monto": None, "moneda": None, "tc": None}


def test_f03_ca_16_alta_siempre_vacia(e2e):
    """F-03-CA-16: «+ Agregar ítem» abre el formulario vacío, y vuelve a abrirse
    vacío después de guardar un ítem."""

    _obra(e2e)
    at = _abrir_nuevo(_plata(e2e))
    assert _campos_nuevo(at) == VACIO

    at.selectbox(key="nuevo_item_rubro").set_value(_rubro(e2e, "Cubierta"))
    at.text_input(key="nuevo_item_descripcion").input("Chapa y aislación")
    at.number_input(key="nuevo_item_monto").set_value(2_400_000.0)
    at.radio(key="nuevo_item_moneda").set_value("ARS")
    at = at.button(key="item_nuevo_agregar").click().run()

    assert not at.exception
    assert "Ítem agregado: Cubierta · ARS 2.400.000." in texts(at)
    assert not any(k.startswith("nuevo_item_") for k in at.session_state.filtered_state)
    assert _expanders(at) == ["Chapa y aislación — ARS 2.400.000"]
    assert [i["descripcion"] for i in _vigentes(e2e)] == ["Chapa y aislación"]

    at = _abrir_nuevo(at)
    assert _campos_nuevo(at) == VACIO


def test_f03_ca_16b_cancelar_alta(e2e):
    """F-03-CA-16: Cancelar cierra el alta sin guardar; al reabrir está vacío."""

    _obra(e2e)
    at = _abrir_nuevo(_plata(e2e))
    at.text_input(key="nuevo_item_descripcion").input("Borrador")
    at = at.button(key="item_nuevo_cancelar").click().run()

    assert finanzas.list_presupuesto(e2e.db, 1) == []
    assert any(b.label == "+ Agregar ítem" for b in at.button)
    assert _campos_nuevo(_abrir_nuevo(at)) == VACIO


@pytest.mark.parametrize(
    "rubro, moneda, monto, falta",
    [
        (None, "ARS", 1000.0, "elegí un rubro"),
        ("Pintura", None, 1000.0, "elegí la moneda"),
        (None, None, None, "elegí un rubro, elegí la moneda"),
    ],
)
def test_f03_ca_17_alta_incompleta_no_guarda_y_conserva(e2e, rubro, moneda, monto, falta):
    """F-03-CA-17: sin rubro o moneda no se guarda, el mensaje dice qué falta y lo
    escrito se conserva. El monto ya no es obligatorio (#35 D9)."""

    _obra(e2e)
    at = _abrir_nuevo(_plata(e2e))
    if rubro:
        at.selectbox(key="nuevo_item_rubro").set_value(_rubro(e2e, rubro))
    at.text_input(key="nuevo_item_descripcion").input("Látex exterior")
    if monto is not None:
        at.number_input(key="nuevo_item_monto").set_value(monto)
    if moneda:
        at.radio(key="nuevo_item_moneda").set_value(moneda)
    at = at.button(key="item_nuevo_agregar").click().run()

    assert f"No se agregó el ítem: {falta}." in texts(at)
    assert finanzas.list_presupuesto(e2e.db, 1) == []
    assert at.text_input(key="nuevo_item_descripcion").value == "Látex exterior"


def test_f03_ca_17b_monto_negativo_no_se_puede(e2e):
    """F-03-CA-17 / D9: el monto puede ser 0, pero nunca negativo (el campo no lo
    permite y el dominio tampoco)."""

    _obra(e2e)
    at = _abrir_nuevo(_plata(e2e))
    assert at.number_input(key="nuevo_item_monto").proto.min == 0.0
    with pytest.raises(finanzas.FinanzasError, match="negativo"):
        finanzas.parse_monto_item(-1)


# --------------------------------------------------------------------------- #
# Edición
# --------------------------------------------------------------------------- #
def test_f03_ca_18_editar_muestra_valores_actuales(e2e):
    """F-03-CA-18: Editar abre el formulario con los valores actuales y con
    Guardar cambios y Cancelar."""

    _obra(e2e)
    item = _item(e2e, "Honorarios", 6000, moneda="USD", descripcion="Dirección de obra")
    at = _abrir_edicion(_plata(e2e), item["id"])
    k = f"editar_item_{item['id']}_"

    assert at.selectbox(key=f"{k}rubro").value == _rubro(e2e, "Honorarios")
    assert at.text_input(key=f"{k}descripcion").value == "Dirección de obra"
    assert at.number_input(key=f"{k}monto").value == 6000.0
    assert at.radio(key=f"{k}moneda").value == "USD"
    assert at.number_input(key=f"{k}tc").value == 1200.0
    etiquetas = [b.label for b in _tab(at).button]
    assert "Guardar cambios" in etiquetas and "Cancelar" in etiquetas


def test_f03_ca_19_guardar_cambios(e2e):
    """F-03-CA-19: cambiar monto y rubro y guardar actualiza el ítem y los
    subtotales y cierra el formulario."""

    _obra(e2e)
    item = _item(e2e, "Fundaciones", 1_000_000, descripcion="Platea")
    _item(e2e, "Estructura", 2_000_000, descripcion="Columnas")
    at = _abrir_edicion(_plata(e2e), item["id"])
    k = f"editar_item_{item['id']}_"
    at.selectbox(key=f"{k}rubro").set_value(_rubro(e2e, "Estructura"))
    at.number_input(key=f"{k}monto").set_value(1_250_000.0)
    at = at.button(key=f"item_guardar_{item['id']}").click().run()

    assert not at.exception
    assert "Cambios guardados." in texts(at)
    guardado = finanzas.get_presupuesto_item(e2e.db, item["id"])
    assert (guardado["rubro_id"], Decimal(guardado["monto"])) == (
        _rubro(e2e, "Estructura"),
        Decimal("1250000"),
    )
    assert guardado["fecha"] == item["fecha"] and guardado["obra_id"] == item["obra_id"]
    assert _grupos(at) == ["**Estructura** · 2 ítems · Subtotal ARS 3.250.000"]
    assert f"{k}monto" not in at.session_state.filtered_state  # formulario cerrado


def test_f03_ca_19b_cotizacion_editada_queda_manual(e2e):
    """F-03-CA-19 (R9): cambiar la cotización la deja como corregida a mano."""

    _obra(e2e)
    item = _item(e2e, "Honorarios", 1000, moneda="USD", descripcion="Proyecto")
    at = _abrir_edicion(_plata(e2e), item["id"])
    at.number_input(key=f"editar_item_{item['id']}_tc").set_value(1150.0)
    at = at.button(key=f"item_guardar_{item['id']}").click().run()

    guardado = finanzas.get_presupuesto_item(e2e.db, item["id"])
    assert (guardado["tipo_cambio"], guardado["tipo_cambio_origen"]) == ("1150.0000", "manual")
    assert "MEP 1.150,00 (corregida a mano)" in _markdown(at).replace("\\", "")


def test_f03_ca_20_cancelar_edicion(e2e):
    """F-03-CA-20: Cancelar descarta los cambios y vuelve al detalle original."""

    _obra(e2e)
    item = _item(e2e, "Pintura", 800_000, descripcion="Látex")
    at = _abrir_edicion(_plata(e2e), item["id"])
    k = f"editar_item_{item['id']}_"
    at.number_input(key=f"{k}monto").set_value(1.0)
    at.text_input(key=f"{k}descripcion").input("Cambiado")
    at = at.button(key=f"item_cancelar_{item['id']}").click().run()

    assert finanzas.get_presupuesto_item(e2e.db, item["id"])["descripcion"] == "Látex"
    assert "- **Descripción:** Látex" in _markdown(at).replace("\\", "")
    # Reabrir la edición muestra otra vez los valores guardados, no los descartados.
    at = _abrir_edicion(at, item["id"])
    assert at.text_input(key=f"{k}descripcion").value == "Látex"
    assert at.number_input(key=f"{k}monto").value == 800_000.0


def test_f03_ca_21_edicion_invalida_conserva_lo_escrito(e2e, monkeypatch):
    """F-03-CA-21: si guardar falla, muestra el error, no guarda y el formulario
    conserva lo escrito."""

    _obra(e2e)
    item = _item(e2e, "Pintura", 800_000, descripcion="Látex")
    at = _abrir_edicion(_plata(e2e), item["id"])
    k = f"editar_item_{item['id']}_"
    at.text_input(key=f"{k}descripcion").input("Látex exterior")
    at.number_input(key=f"{k}monto").set_value(1.0)

    def falla(*_, **__):
        raise finanzas.FinanzasError("El monto es demasiado grande.")

    monkeypatch.setattr(finanzas, "update_presupuesto_item", falla)
    at = at.button(key=f"item_guardar_{item['id']}").click().run()

    assert "No se guardaron los cambios: El monto es demasiado grande." in texts(at)
    assert Decimal(finanzas.get_presupuesto_item(e2e.db, item["id"])["monto"]) == 800_000
    assert at.text_input(key=f"{k}descripcion").value == "Látex exterior"
    assert any(b.label == "Guardar cambios" for b in _tab(at).button)


# --------------------------------------------------------------------------- #
# Borrado
# --------------------------------------------------------------------------- #
def test_f03_ca_22_borrar_pide_confirmacion_y_cancelar_no_cambia(e2e):
    """F-03-CA-22: Borrar abre un diálogo que nombra el ítem; Cancelar no cambia nada."""

    _obra(e2e)
    item = _item(e2e, "Estructura", 3_200_000, descripcion="Hierro del 8")
    at = _pedir_borrado(_plata(e2e), item["id"])

    dialogo = "\n".join(m.value for m in at.markdown).replace("\\", "")
    assert "Vas a borrar **Hierro del 8** de **Estructura** por **ARS 3.200.000**." in dialogo
    assert "Queda guardado en el historial" in dialogo
    assert finanzas.get_presupuesto_item(e2e.db, item["id"])["anulado"] is False

    at = at.button(key="item_borrar_cancelar").click().run()
    assert finanzas.get_presupuesto_item(e2e.db, item["id"])["anulado"] is False
    assert _expanders(at) == ["Hierro del 8 — ARS 3.200.000"]
    assert "Vas a borrar" not in "\n".join(m.value for m in at.markdown)


def test_f03_ca_22b_confirmar_oculta_y_conserva(e2e):
    """F-03-CA-22 (R10): confirmar lo saca de la lista y de los totales, y queda
    anulado en la base."""

    _obra(e2e)
    borrar = _item(e2e, "Estructura", 3_200_000, descripcion="Hierro del 8")
    _item(e2e, "Estructura", 1_000_000, descripcion="Hormigón")
    at = _pedir_borrado(_plata(e2e), borrar["id"])
    at = at.button(key="item_borrar_confirmar").click().run()

    assert not at.exception
    assert "Ítem borrado del presupuesto." in texts(at)
    assert _expanders(at) == ["Hormigón — ARS 1.000.000"]
    assert _grupos(at) == ["**Estructura** · 1 ítem · Subtotal ARS 1.000.000"]
    assert {m.label: m.value for m in _tab(at).metric}["Presupuestado"] == "ARS 1.000.000"
    en_base = finanzas.get_presupuesto_item(e2e.db, borrar["id"])
    assert en_base["anulado"] is True and en_base["descripcion"] == "Hierro del 8"


def test_f03_ca_22c_cerrar_el_dialogo_no_borra(e2e, monkeypatch):
    """F-03-CA-22: cerrar el diálogo (X o Esc) equivale a cancelar.

    Streamlit llama a on_dismiss al cerrarlo; verificamos que esté conectado a la
    función que descarta el pedido, y el efecto de descartarlo."""

    import streamlit

    import plata_ui

    opciones = {}
    real = streamlit.dialog

    def espia(titulo, **kwargs):
        opciones.update(kwargs, titulo=titulo)
        return real(titulo, **kwargs)

    monkeypatch.setattr(streamlit, "dialog", espia)
    _obra(e2e)
    item = _item(e2e, "Pintura", 100, descripcion="Muestra")
    at = _pedir_borrado(_plata(e2e), item["id"])

    assert opciones["titulo"] == "¿Borrar este ítem del presupuesto?"
    assert opciones["on_dismiss"] is plata_ui._cancelar_borrado
    del at.session_state[plata_ui._A_BORRAR]  # lo que hace _cancelar_borrado
    at = at.run()
    assert "Vas a borrar" not in "\n".join(m.value for m in at.markdown)
    assert finanzas.get_presupuesto_item(e2e.db, item["id"])["anulado"] is False


def test_f03_ca_22d_borrar_el_item_en_edicion(e2e):
    """F-03-CA-22: si se borra un ítem que estaba en edición, la edición se cierra."""

    _obra(e2e)
    item = _item(e2e, "Pintura", 100, descripcion="Muestra")
    at = _abrir_edicion(_plata(e2e), item["id"])
    at.session_state["item_a_borrar"] = item["id"]
    at = at.run().button(key="item_borrar_confirmar").click().run()

    assert finanzas.get_presupuesto_item(e2e.db, item["id"])["anulado"] is True
    assert "item_editando" not in at.session_state
    assert "Todavía no hay ítems en el presupuesto de esta obra." in texts(at)


# --------------------------------------------------------------------------- #
# Seguridad, accesibilidad y gastos
# --------------------------------------------------------------------------- #
MALICIOSO = "![x](https://evil.test/p.png) [link](https://evil.test)"


def test_f03_ca_23_texto_con_markdown_no_se_interpreta(e2e):
    """F-03-CA-23: descripción con Markdown se muestra como texto en la lista, el
    detalle, el diálogo de borrado y el aviso de alta."""

    _obra(e2e)
    item = _item(e2e, "Pintura", 100, descripcion=MALICIOSO)
    at = _plata(e2e)
    crudos = [e.label for e in _tab(at).expander] + [m.value for m in _tab(at).markdown]
    at = _pedir_borrado(at, item["id"])
    crudos += [m.value for m in at.markdown]

    assert crudos
    for texto in crudos:
        assert "](https://" not in texto, texto
    assert any(r"\!\[x\]" in t for t in crudos)


def test_f03_ca_23b_aviso_de_alta_escapado(e2e):
    """F-03-CA-23: el aviso «Ítem agregado» no interpreta el nombre del rubro."""

    _obra(e2e)
    malo = e2e.db.table("rubros").insert({"nombre": MALICIOSO, "orden": 5}).execute().data[0]
    at = _abrir_nuevo(_plata(e2e))
    at.selectbox(key="nuevo_item_rubro").set_value(malo["id"])
    at.number_input(key="nuevo_item_monto").set_value(100.0)
    at.radio(key="nuevo_item_moneda").set_value("ARS")
    at = at.button(key="item_nuevo_agregar").click().run()

    exitos = [m.value for m in at.success]
    assert exitos and all("](https://" not in e for e in exitos)


def test_f03_ca_23c_campos_con_etiqueta(e2e):
    """Accesibilidad: todos los campos del alta y de la edición tienen etiqueta
    visible; los obligatorios lo dicen; las acciones son botones con texto."""

    _obra(e2e)
    item = _item(e2e, "Pintura", 100, descripcion="Muestra")
    at = _abrir_edicion(_abrir_nuevo(_plata(e2e)), item["id"])
    tab = _tab(at)
    campos = [*tab.number_input, *tab.text_input, *tab.selectbox, *tab.radio]
    propios = [c for c in campos if c.key and c.key.startswith(("nuevo_item_", "editar_item_"))]

    assert len(propios) == 10
    for c in propios:
        assert c.label and c.label.strip(), c.key
    obligatorios = {c.key.split("_item_")[-1] for c in propios if "obligatori" in c.label}
    assert {k.split("_")[-1] for k in obligatorios} == {"rubro", "moneda"}  # monto: D9
    for b in tab.button:
        assert b.label.strip(), b.key


def test_f03_ca_24_no_se_puede_mover_un_item_de_obra(e2e):
    """F-03-CA-24 (dominio): la edición solo toca los campos permitidos.

    La base lo garantiza con permisos por columna (tests/sql y LIVE-19)."""

    _obra(e2e)
    item = _item(e2e, "Pintura", 100, descripcion="Muestra")
    llamadas = []
    original = e2e.db.table

    def espiar(nombre):
        query = original(nombre)
        update = query.update

        def registrar(payload):
            llamadas.append((nombre, dict(payload)))
            return update(payload)

        query.update = registrar
        return query

    e2e.db.table = espiar
    finanzas.update_presupuesto_item(
        e2e.db,
        item["id"],
        monto=200,
        moneda="ARS",
        rubro_id=_rubro(e2e, "Pintura"),
        descripcion="Otra",
    )
    assert llamadas and all(
        set(payload) <= set(finanzas.CAMPOS_EDITABLES_ITEM) for _, payload in llamadas
    )
