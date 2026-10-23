"""F-03 · Presupuesto y gastos, end to end through the real app.

Every gasto belongs to a budget item and is added, listed and cancelled inside
it (#35). One test (or more) per acceptance criterion; IDs match the ficha and
docs/casos-e2e.md. External services are simulated (see conftest.py).
"""

import re
from datetime import timedelta

import pytest
from langchain_core.messages import AIMessage

from atrium import finanzas, obras, proveedores
from tests.e2e.conftest import (
    abrir_presupuesto,
    click,
    confirmar_propuestas,
    tabla_items,
    tabla_rubros,
    texts,
)
from tests.fakes import tool_call

PRESUPUESTO = 2  # index of the «Presupuesto» tab in 🏗️ Obra activa (#49)


def _obra(e2e, nombre="Casa Lote 12", **extra):
    return obras.create_obra(e2e.db, {"nombre": nombre, "municipio": "La Plata", **extra})


def _rubro(e2e, nombre):
    return finanzas.find_rubros(e2e.db, nombre)[0]["id"]


def _item(e2e, rubro, monto=0, moneda="ARS", descripcion=None, **extra):
    item, _ = finanzas.add_presupuesto_item(
        e2e.db,
        1,
        monto=monto,
        moneda=moneda,
        rubro_id=_rubro(e2e, rubro),
        descripcion=descripcion or f"Ítem de {rubro}",
        **extra,
    )
    return item


def _plata(e2e, obra_id=1):
    """Presupuesto of the obra, with every rubro and ítem of the table expanded."""

    at = e2e.go_to_obras(e2e.login())
    return abrir_presupuesto(e2e.elegir_obra(at, obra_id), e2e.db)


def visible(at) -> str:
    """Page text as the user reads it (Markdown escapes removed)."""

    return re.sub(r"\\(.)", r"\1", texts(at))


def _metricas(at):
    return {m.label: m.value for m in at.tabs[PRESUPUESTO].metric}


class _Tabla:
    """Rubro rows of the budget table, read like the old dataframe: .loc[rubro, col]."""

    def __init__(self, filas):
        self.filas = filas
        self.index = list(filas)
        self.loc = self

    def __getitem__(self, clave):
        rubro, columna = clave
        return self.filas[rubro][columna]


def _tabla(at):
    """The rubro rows of the budget table (#45), indexed by rubro."""

    return _Tabla(tabla_rubros(at))


def _titulos(at) -> list[str]:
    """Ítem rows as one line: «name — presupuestado · gastado X · % · estado»."""

    lineas = []
    for f in tabla_items(at):
        partes = [f"{f['nombre']} — {f['Presupuestado'].split(':gray')[0].strip()}"]
        partes.append(f"gastado {f['Gastado']}")
        if f["% consumido"] != "sin presupuesto":
            partes.append(f["% consumido"])
        partes.append(f["Estado"])
        lineas.append(" · ".join(partes))
    return lineas


def _abrir_gasto(at, item_id):
    return at.button(key=f"gasto_agregar_{item_id}").click().run()


def _cargar_gasto(at, item_id, monto, descripcion, moneda=None, **mas):
    """«Registrar un gasto» inside the item, fill the form and save."""

    at = _abrir_gasto(at, item_id)
    k = f"nuevo_gasto_{item_id}_"
    if monto is not None:
        at.number_input(key=f"{k}monto").set_value(monto)
    if moneda:
        at.radio(key=f"{k}moneda").set_value(moneda)
    at.text_input(key=f"{k}descripcion").input(descripcion)
    if "fecha" in mas:
        at.date_input(key=f"{k}fecha").set_value(mas["fecha"])
    if "proveedor" in mas:
        at.selectbox(key=f"{k}proveedor_id").set_value(mas["proveedor"])
    return at.button(key=f"gasto_guardar_{item_id}").click().run()


def _proveedor(e2e, nombre, **datos):
    """A proveedor of the shared list (#37)."""

    return proveedores.create_proveedor(e2e.db, {"nombre": nombre, **datos})


def _seed_gasto(e2e, monto, moneda, rubro, tipo_cambio=None, item=None, **mas):
    """Insert a gasto directly (bypassing the UI) with a fixed rate or none.

    Without ``item`` it goes to the first vigent item of ``rubro`` (created at 0).
    """

    if item is None:
        del_rubro = [
            i
            for i in finanzas.list_presupuesto(e2e.db, 1)
            if i["rubro_id"] == _rubro(e2e, rubro) and not i["anulado"]
        ]
        item = del_rubro[0] if del_rubro else _item(e2e, rubro)
    fila = {
        "presupuesto_item_id": item["id"],
        "obra_id": item["obra_id"],
        "rubro_id": item["rubro_id"],
        "fecha": finanzas.hoy().isoformat(),
        "monto": str(monto),
        "moneda": moneda,
        "descripcion": mas.get("descripcion", "Gasto de prueba"),
    }
    if tipo_cambio:
        fila.update(tipo_cambio=str(tipo_cambio), tipo_cambio_origen="auto")
    return e2e.db.table("gastos").insert(fila).execute().data[0]


# --------------------------------------------------------------------------- #
# Gastos dentro de cada ítem (#35)
# --------------------------------------------------------------------------- #
def test_f03_ca_27_agregar_gasto_en_un_item(e2e):
    """F-03-CA-27: «Registrar un gasto» dentro del ítem guarda el gasto en ese ítem y
    actualiza el ítem, el rubro y los totales."""

    _obra(e2e)
    item = _item(e2e, "Estructura", 1_000_000, descripcion="Hierro del 8")
    hierros = _proveedor(e2e, "Hierros Sur")
    at = _cargar_gasto(
        _plata(e2e), item["id"], 350_000.0, "Primera entrega", proveedor=hierros["id"]
    )

    assert not at.exception
    assert "Gasto registrado en «Hierro del 8»: ARS 350.000" in visible(at)
    gasto = finanzas.list_gastos(e2e.db, 1)[0]
    assert gasto["presupuesto_item_id"] == item["id"]
    assert gasto["proveedor_id"] == hierros["id"]
    pantalla = visible(at)
    assert "Primera entrega" in pantalla and "Hierros Sur" in pantalla
    assert _titulos(at) == [
        "Hierro del 8 — ARS 1.000.000 · gastado ARS 350.000 · 35% · 🟢 Dentro del presupuesto"
    ]
    assert "Saldo: ARS 650.000" in pantalla
    assert _tabla(at).loc["Estructura", "Gastado"] == "ARS 350.000"
    assert _metricas(at)["Gastado"] == "ARS 350.000"
    assert _metricas(at)["Desvío"] == "−ARS 650.000"
    # El formulario se cierra y, al reabrirlo, está vacío.
    at = _abrir_gasto(at, item["id"])
    assert at.text_input(key=f"nuevo_gasto_{item['id']}_descripcion").value == ""
    assert at.number_input(key=f"nuevo_gasto_{item['id']}_monto").value is None


def test_f03_ca_27b_formulario_nombra_el_item_y_precarga_su_moneda(e2e):
    """F-03-CA-27 / R15: el formulario nombra el ítem y arranca en la moneda del
    ítem, que se puede cambiar."""

    _obra(e2e)
    item = _item(e2e, "Honorarios", 1000, moneda="USD", descripcion="Proyecto")
    at = _abrir_gasto(_plata(e2e), item["id"])
    k = f"nuevo_gasto_{item['id']}_"

    assert "Nuevo gasto en «Proyecto»" in visible(at)
    assert at.radio(key=f"{k}moneda").value == "USD"
    assert at.number_input(key=f"{k}monto").value is None
    assert at.text_input(key=f"{k}descripcion").value == ""

    at.number_input(key=f"{k}monto").set_value(120_000.0)
    at.radio(key=f"{k}moneda").set_value("ARS")
    at.text_input(key=f"{k}descripcion").input("Copias")
    at = at.button(key=f"gasto_guardar_{item['id']}").click().run()
    assert finanzas.list_gastos(e2e.db, 1)[0]["moneda"] == "ARS"


def test_f03_ca_27c_cancelar_no_guarda(e2e):
    _obra(e2e)
    item = _item(e2e, "Pintura", 100)
    at = _abrir_gasto(_plata(e2e), item["id"])
    at.text_input(key=f"nuevo_gasto_{item['id']}_descripcion").input("Borrador")
    at = at.button(key=f"gasto_cancelar_{item['id']}").click().run()

    assert finanzas.list_gastos(e2e.db, 1) == []
    boton = at.button(key=f"gasto_agregar_{item['id']}")
    assert boton.help == "Registrar un gasto en Ítem de Pintura" and not boton.disabled


def test_f03_ca_28_datos_faltantes_no_se_guardan(e2e):
    """F-03-CA-28 (antes CA-10): sin monto o sin descripción no se guarda, dice qué
    falta y conserva lo escrito."""

    _obra(e2e)
    item = _item(e2e, "Fundaciones", 1000)
    k = f"nuevo_gasto_{item['id']}_"
    at = _cargar_gasto(_plata(e2e), item["id"], None, "Cemento")
    assert "No se agregó el gasto: ingresá un monto mayor que cero." in visible(at)
    assert at.text_input(key=f"{k}descripcion").value == "Cemento"

    at.number_input(key=f"{k}monto").set_value(1000.0)
    at.text_input(key=f"{k}descripcion").input("   ")
    at = at.button(key=f"gasto_guardar_{item['id']}").click().run()
    assert "No se agregó el gasto: escribí una descripción." in visible(at)
    assert at.number_input(key=f"{k}monto").value == 1000.0
    assert finanzas.list_gastos(e2e.db, 1) == []


def test_f03_ca_3_cotizacion_automatica_del_dia(e2e):
    """F-03-CA-3: MEP compra 1190 / venta 1210 -> se guarda 1200 automático."""

    _obra(e2e)
    e2e.set_mep({finanzas.hoy(): (1190, 1210)})
    item = _item(e2e, "Honorarios", 1000, moneda="USD")
    at = _cargar_gasto(_plata(e2e), item["id"], 100.0, "Visita técnica")

    gasto = finanzas.list_gastos(e2e.db, 1)[0]
    assert (gasto["tipo_cambio"], gasto["tipo_cambio_origen"]) == ("1200.0000", "auto")
    assert "MEP 1.200,00 (automática)" in visible(at)


def test_f03_ca_4_sabado_usa_cotizacion_del_viernes(e2e):
    """F-03-CA-4: un gasto de un sábado toma la cotización del viernes anterior."""

    hoy = finanzas.hoy()
    sabado = hoy - timedelta(days=(hoy.weekday() - 5) % 7)
    viernes = sabado - timedelta(days=1)
    e2e.set_mep({viernes: (1180, 1200), viernes - timedelta(days=1): (1000, 1000)})
    _obra(e2e)
    item = _item(e2e, "Mampostería")

    at = _cargar_gasto(_plata(e2e), item["id"], 50_000.0, "Arena", fecha=sabado)

    assert not at.exception
    gasto = finanzas.list_gastos(e2e.db, 1)[0]
    assert gasto["fecha"] == sabado.isoformat()
    assert gasto["tipo_cambio"] == "1190.0000"


def test_f03_ca_5_fuente_caida_guarda_sin_cotizacion(e2e):
    """F-03-CA-5: sin servicio de cotizaciones el gasto se guarda, con aviso, y se
    puede cargar la cotización a mano."""

    _obra(e2e)
    e2e.mep_caido = True
    item = _item(e2e, "Fundaciones")
    at = _cargar_gasto(_plata(e2e), item["id"], 80_000.0, "Cemento")

    assert not at.exception
    gasto = finanzas.list_gastos(e2e.db, 1)[0]
    assert "tipo_cambio" not in gasto
    assert "No se pudo consultar el dólar MEP" in visible(at)
    assert "sin cotización" in texts(at)
    assert at.button(key=f"gasto_editar_{gasto['id']}").help == "Editar este gasto"


def test_f03_ca_6_corregir_cotizacion_a_mano(e2e):
    """F-03-CA-6: la cotización corregida queda manual, se marca y se usa en el resumen."""

    _obra(e2e)
    gasto = _seed_gasto(e2e, 1000, "USD", "Honorarios", tipo_cambio=1200)
    at = _plata(e2e).button(key=f"gasto_editar_{gasto['id']}").click().run()
    at.number_input(key=f"editar_gasto_{gasto['id']}_tc").set_value(1180.0)
    at = at.button(key=f"gasto_guardar_{gasto['id']}_ed").click().run()

    assert not at.exception
    gasto = finanzas.list_gastos(e2e.db, 1)[0]
    assert (gasto["tipo_cambio"], gasto["tipo_cambio_origen"]) == ("1180.0000", "manual")
    assert "MEP 1.180,00 (corregida a mano)" in visible(at)
    assert _metricas(at)["Gastado"] == "ARS 1.180.000"


# --------------------------------------------------------------------------- #
# Resumen, monedas y semáforo
# --------------------------------------------------------------------------- #
def test_f03_ca_7_resumen_en_pesos_y_en_dolares(e2e):
    """F-03-CA-7: USD 1.000 y ARS 600.000 a 1200 -> ARS 1.800.000 o USD 1.500."""

    _obra(e2e)
    _seed_gasto(e2e, 1000, "USD", "Honorarios", tipo_cambio=1200)
    _seed_gasto(e2e, 600000, "ARS", "Estructura", tipo_cambio=1200)
    at = _plata(e2e)
    assert _metricas(at)["Gastado"] == "ARS 1.800.000"

    at = at.radio(key="plata_moneda").set_value("USD").run()
    assert _metricas(at)["Gastado"] == "USD 1.500"
    assert _tabla(at).loc["Estructura", "Gastado"] == "USD 500"


def test_f03_ca_8_sin_cotizacion_total_incompleto(e2e):
    """F-03-CA-8: un gasto en USD sin cotización no suma en ARS y hay aviso."""

    _obra(e2e)
    _seed_gasto(e2e, 1000, "USD", "Honorarios")
    _seed_gasto(e2e, 600000, "ARS", "Estructura")
    at = _plata(e2e)

    assert _metricas(at)["Gastado"] == "ARS 600.000"
    assert "Total incompleto: 1 registro(s) sin cotización" in texts(at)


def test_f03_ca_31_gasto_en_otra_moneda_que_su_item(e2e):
    """F-03-CA-31: un gasto en USD en un ítem en ARS se convierte con la cotización
    del gasto; sin cotización, el ítem avisa «total incompleto»."""

    _obra(e2e)
    item = _item(e2e, "Carpinterías", 2_000_000, descripcion="Aberturas")
    _seed_gasto(e2e, 500, "USD", "Carpinterías", tipo_cambio=1400, item=item)
    at = _plata(e2e)
    assert _titulos(at)[0].startswith("Aberturas — ARS 2.000.000 · gastado ARS 700.000 · 35%")

    _seed_gasto(e2e, 100, "USD", "Carpinterías", item=item)
    at = _plata(e2e)
    assert _titulos(at)[0].endswith("· total incompleto")
    assert "1 registro(s) en otra moneda sin cotización" in texts(at)


@pytest.mark.parametrize(
    "gastado, porcentaje, estado",
    [
        (89_000, "89%", "🟢 Dentro del presupuesto"),
        (90_000, "90%", "🟡 Cerca del límite"),
        (100_000, "100%", "🟡 Cerca del límite"),
        (101_000, "101%", "🔴 Excedido"),
    ],
)
def test_f03_ca_26_semaforo_por_item(e2e, gastado, porcentaje, estado):
    """F-03-CA-26 / R16: cada ítem muestra total, gastado y % consumido, con el
    estado en palabras además del color."""

    _obra(e2e)
    item = _item(e2e, "Pintura", 100_000, descripcion="Látex")
    _seed_gasto(e2e, gastado, "ARS", "Pintura", tipo_cambio=1200, item=item)
    at = _plata(e2e)

    titulo = _titulos(at)[0]
    assert titulo.startswith("Látex — ARS 100.000 · gastado ARS ")
    assert f"· {porcentaje} · {estado}" in titulo
    estado_item = tabla_items(at)[0]["Estado"]
    assert estado_item == estado  # en palabras, no solo el color


def test_f03_ca_26b_gastos_del_item_y_saldo(e2e):
    """F-03-CA-26: al abrir un ítem se ven sus gastos, el saldo y el estado."""

    _obra(e2e)
    item = _item(e2e, "Estructura", 9_000_000, descripcion="Hierro")
    otro = _item(e2e, "Estructura", 1_000, descripcion="Otro")
    _seed_gasto(e2e, 2_000_000, "ARS", "", tipo_cambio=1200, item=item, descripcion="Entrega 1")
    _seed_gasto(e2e, 5, "ARS", "", tipo_cambio=1200, item=otro, descripcion="De otro ítem")
    at = _plata(e2e)

    hierro = next(f for f in tabla_items(at) if f["nombre"] == "Hierro")
    assert (hierro["Presupuestado"], hierro["Gastado"], hierro["% consumido"]) == (
        "ARS 9.000.000",
        "ARS 2.000.000",
        "22%",
    )
    assert "Saldo: ARS 7.000.000" in visible(at)
    entrega = [m.value for m in at.tabs[PRESUPUESTO].markdown if "Entrega 1" in m.value]
    assert len(entrega) == 1  # aparece solo dentro de su ítem


def test_f03_ca_30d_item_en_cero(e2e):
    """F-03-CA-30d / D9: un ítem se puede crear sin monto (queda en 0) y muestra
    «Sin presupuesto asignado»."""

    _obra(e2e)
    at = click(_plata(e2e), "+ Agregar ítem")
    at.selectbox(key="nuevo_item_rubro").set_value(_rubro(e2e, "Pintura"))
    at.text_input(key="nuevo_item_descripcion").input("Látex exterior")
    at.radio(key="nuevo_item_moneda").set_value("ARS")
    at = at.button(key="item_nuevo_agregar").click().run()

    assert not at.exception
    assert finanzas.list_presupuesto(e2e.db, 1)[0]["monto"] == "0.00"
    assert _titulos(at) == ["Látex exterior — ARS 0 · gastado ARS 0 · ⚪ Sin presupuesto asignado"]


def test_f03_ca_35_cambiar_rubro_mueve_los_gastos(e2e):
    """F-03-CA-35: al cambiar el rubro del ítem, sus gastos pasan a ese rubro."""

    _obra(e2e)
    item = _item(e2e, "Pintura", 100, descripcion="Muestra")
    _seed_gasto(e2e, 40, "ARS", "Pintura", tipo_cambio=1200, item=item)
    at = _plata(e2e).button(key=f"item_editar_{item['id']}").click().run()
    at.selectbox(key=f"editar_item_{item['id']}_rubro").set_value(_rubro(e2e, "Revoques"))
    at = at.button(key=f"item_guardar_{item['id']}").click().run()

    assert "Pintura" not in _tabla(at).index
    assert _tabla(at).loc["Revoques", "Gastado"] == "ARS 40"


# --------------------------------------------------------------------------- #
# Anular gastos y borrar ítems con gastos
# --------------------------------------------------------------------------- #
def test_f03_ca_29_anular_gasto(e2e):
    """F-03-CA-29 (antes CA-9): anular pide confirmación; cancelar no cambia nada;
    confirmar lo tacha, deja de sumar y sigue en la base."""

    _obra(e2e)
    gasto = _seed_gasto(e2e, 350000, "ARS", "Estructura", tipo_cambio=1200, descripcion="Hierro")
    at = _plata(e2e).button(key=f"gasto_anular_{gasto['id']}").click().run()

    dialogo = "\n".join(m.value for m in at.markdown).replace("\\", "")
    assert "Vas a anular **Hierro**" in dialogo and "**ARS 350.000**" in dialogo
    at = at.button(key="gasto_anular_cancelar").click().run()
    assert finanzas.list_gastos(e2e.db, 1)[0]["anulado"] is False
    assert _metricas(at)["Gastado"] == "ARS 350.000"

    at = at.button(key=f"gasto_anular_{gasto['id']}").click().run()
    at = at.button(key="gasto_anular_confirmar").click().run()

    assert not at.exception
    assert finanzas.list_gastos(e2e.db, 1)[0]["anulado"] is True  # sigue en la base
    assert _metricas(at)["Gastado"] == "ARS 0"
    tachado = [m.value for m in at.tabs[PRESUPUESTO].markdown if m.value.startswith("~~")]
    assert tachado and "Hierro" in tachado[0] and tachado[0].endswith("**Anulado**")
    assert f"gasto_anular_{gasto['id']}" not in [b.key for b in at.button]


def test_f03_ca_29b_dialogo_conectado_a_cancelar(e2e, monkeypatch):
    """F-03-CA-29: cerrar el diálogo (X o Esc) equivale a cancelar."""

    import streamlit

    import plata_ui

    opciones = {}
    real = streamlit.dialog

    def espia(titulo, **kwargs):
        opciones.update(kwargs, titulo=titulo)
        return real(titulo, **kwargs)

    monkeypatch.setattr(streamlit, "dialog", espia)
    _obra(e2e)
    gasto = _seed_gasto(e2e, 10, "ARS", "Pintura", tipo_cambio=1200)
    _plata(e2e).button(key=f"gasto_anular_{gasto['id']}").click().run()

    assert opciones["titulo"] == "¿Anular este gasto?"
    assert opciones["on_dismiss"] is plata_ui._cancelar_anulacion


def test_f03_ca_30_borrar_item_con_gastos(e2e):
    """F-03-CA-30 / R12b: el diálogo avisa que el ítem tiene gastos; confirmar borra
    el ítem y sus gastos, que siguen en la base."""

    _obra(e2e)
    item = _item(e2e, "Estructura", 9_000_000, descripcion="Hierro del 8")
    for monto in (2_000_000, 1_200_000):
        _seed_gasto(e2e, monto, "ARS", "", tipo_cambio=1200, item=item)
    at = _plata(e2e).button(key=f"item_borrar_{item['id']}").click().run()

    aviso = visible(at)
    assert "Este ítem tiene 2 gasto(s) asociado(s) por ARS 3.200.000" in aviso
    assert "también se borran sus gastos" in aviso
    assert at.button(key="item_borrar_confirmar").label == "Borrar ítem y gastos"

    at = at.button(key="item_borrar_confirmar").click().run()
    assert not at.exception
    assert "Ítem borrado del presupuesto, con sus 2 gasto(s)." in visible(at)
    assert all(g["anulado"] for g in finanzas.list_gastos(e2e.db, 1))
    assert len(finanzas.list_gastos(e2e.db, 1)) == 2
    assert _metricas(at)["Gastado"] == "ARS 0"


def test_f03_ca_30_borrar_item_sin_gastos_no_avisa(e2e):
    _obra(e2e)
    item = _item(e2e, "Pintura", 100)
    at = _plata(e2e).button(key=f"item_borrar_{item['id']}").click().run()
    assert "gasto(s) asociado(s)" not in visible(at)
    assert at.button(key="item_borrar_confirmar").label == "Borrar ítem"


# --------------------------------------------------------------------------- #
# «Imprevistos»
# --------------------------------------------------------------------------- #
def test_f03_ca_30b_obra_nueva_trae_imprevistos(e2e):
    """F-03-CA-30b / R12: al crear una obra con presupuesto USD 85.000 se agrega
    «Imprevistos» por USD 8.500 en el rubro Otros."""

    at = e2e.ir_a(e2e.login(), "nueva-obra")
    at.text_input(key="nueva_nombre").input("Casa Lote 12")
    at.number_input(key="nueva_presupuesto").set_value(85000.0)
    at.selectbox(key="nueva_moneda").set_value("USD")
    at = click(at, "Crear obra")

    assert not at.exception
    assert "se agregó el ítem «Imprevistos» por USD 8.500" in visible(at)
    item = finanzas.list_presupuesto(e2e.db, 1)[0]
    assert (item["descripcion"], item["monto"], item["moneda"]) == ("Imprevistos", "8500.00", "USD")
    assert item["es_imprevistos"] and item["rubro_id"] == _rubro(e2e, "Otros")
    at = abrir_presupuesto(e2e.elegir_obra(at.run(), 1), e2e.db)
    fila = tabla_items(at)[0]
    assert fila["nombre"] == "Imprevistos" and "USD 8.500" in fila["Presupuestado"]


def test_f03_ca_30c_imprevistos_se_puede_recrear(e2e):
    """F-03-CA-30c: sin «Imprevistos» vigente, el alta ofrece marcar un ítem como
    imprevistos; si ya hay uno, no."""

    _obra(e2e)
    at = click(_plata(e2e), "+ Agregar ítem")
    at.selectbox(key="nuevo_item_rubro").set_value(_rubro(e2e, "Otros"))
    at.radio(key="nuevo_item_moneda").set_value("ARS")
    at.checkbox(key="nuevo_item_imprevistos").check()
    at = at.button(key="item_nuevo_agregar").click().run()

    item = finanzas.list_presupuesto(e2e.db, 1)[0]
    assert item["es_imprevistos"] and item["descripcion"] == "Imprevistos"
    at = click(at, "+ Agregar ítem")
    assert "nuevo_item_imprevistos" not in [c.key for c in at.checkbox]


def test_f03_ca_32_no_hay_gastos_sueltos(e2e):
    """F-03-CA-32: ya no existe el formulario de gasto suelto ni «Últimos gastos»."""

    _obra(e2e)
    _item(e2e, "Pintura", 100)
    pantalla = visible(_plata(e2e))
    assert "Registrar un gasto" not in pantalla and "Últimos gastos" not in pantalla


# --------------------------------------------------------------------------- #
# Agente
# --------------------------------------------------------------------------- #
def _chat(e2e, pedido, *respuestas):
    e2e.script(*respuestas)
    at = e2e.login()
    at = e2e.elegir_obra(at, 1)
    return e2e.abrir_agente(at).chat_input[0].set_value(pedido).run()


def test_f03_ca_33_cargar_gasto_por_chat(e2e):
    """F-03-CA-33 (antes CA-11): «cargá 350 mil de hierro» con un solo ítem que
    coincide -> propone el gasto en ese ítem; al confirmarlo se guarda con la cotización
    del día y se avisa."""

    _obra(e2e)
    item = _item(e2e, "Estructura", 1_000_000, descripcion="Hierro del 8")
    _item(e2e, "Fundaciones", 500, descripcion="Excavación")
    at = _chat(
        e2e,
        "Cargá 350 mil pesos de hierro",
        tool_call("registrar_gasto", {"monto": 350000, "descripcion": "Hierro", "item": "hierro"}),
        AIMessage(content="Te dejé ARS 350.000 en Hierro del 8 para confirmar."),
    )

    assert not at.exception
    assert "Registrar en «Casa Lote 12» un gasto de ARS 350.000 en el ítem «Hierro del 8»" in texts(
        at
    )
    assert finanzas.list_gastos(e2e.db, 1) == []
    at = confirmar_propuestas(at)
    assert "💸 Gasto registrado en «Casa Lote 12»: ARS 350.000 · Hierro del 8" in texts(at)
    gasto = finanzas.list_gastos(e2e.db, 1)[0]
    assert gasto["presupuesto_item_id"] == item["id"] and gasto["moneda"] == "ARS"
    assert gasto["tipo_cambio"] == "1200.0000" and gasto["tipo_cambio_origen"] == "auto"

    at = e2e.go_to_obras(at)
    assert _tabla(at).loc["Estructura", "Gastado"] == "ARS 350.000"


def test_f03_ca_33b_ningun_item_coincide_ofrece_imprevistos(e2e):
    """F-03-CA-33: sin ítem que coincida, no guarda y pregunta (ofrece Imprevistos)."""

    _obra(e2e)
    _item(e2e, "Otros", 0, descripcion="Imprevistos", es_imprevistos=True)
    _chat(
        e2e,
        "Cargá 1000 de jardinería",
        tool_call("registrar_gasto", {"monto": 1000, "descripcion": "x", "item": "jardinería"}),
        AIMessage(content="¿A qué ítem lo cargo?"),
    )

    resultado = e2e.llm.seen[1][-1].content
    assert "No propuse el gasto" in resultado and "«Imprevistos»" in resultado
    assert "Preguntale al usuario" in resultado
    assert finanzas.list_gastos(e2e.db, 1) == []


def test_f03_ca_33c_varios_items_pide_aclarar(e2e):
    """F-03-CA-33: con varios ítems posibles no guarda nada y exige preguntar."""

    _obra(e2e)
    _item(e2e, "Instalación eléctrica", 100, descripcion="Cables planta baja")
    _item(e2e, "Instalación eléctrica", 100, descripcion="Cables planta alta")
    at = _chat(
        e2e,
        "Cargá 1000 de cables",
        tool_call("registrar_gasto", {"monto": 1000, "descripcion": "Cables", "item": "cables"}),
        AIMessage(content="¿Planta baja o alta?"),
    )

    resultado = e2e.llm.seen[1][-1].content
    assert "hay varios ítems que coinciden" in resultado and "Preguntale al usuario" in resultado
    assert "Cables planta baja" in resultado and "Cables planta alta" in resultado
    assert finanzas.list_gastos(e2e.db, 1) == []
    assert "💸" not in texts(at)


def test_f03_ca_12_consultar_desvios_por_chat(e2e):
    """F-03-CA-12: «¿en qué rubro nos pasamos?» responde con datos reales, por
    rubro y por ítem."""

    _obra(e2e)
    fund = _item(e2e, "Fundaciones", 1000, descripcion="Platea")
    estr = _item(e2e, "Estructura", 2000, descripcion="Columnas")
    _seed_gasto(e2e, 1500, "ARS", "", tipo_cambio=1200, item=fund)
    _seed_gasto(e2e, 500, "ARS", "", tipo_cambio=1200, item=estr)
    at = _chat(
        e2e,
        "¿En qué rubro nos pasamos?",
        tool_call("resumen_plata", {}),
        AIMessage(content="Nos pasamos en Fundaciones: ARS 500 por encima."),
    )

    resultado = e2e.llm.seen[1][-1].content
    assert "Fundaciones: presupuestado ARS 1.000, gastado ARS 1.500" in resultado
    assert "(Excedido)" in resultado.split("Fundaciones")[1].split("\n")[0]
    assert "Estructura" in resultado and "(Dentro del presupuesto)" in resultado
    assert "- Platea: total ARS 1.000, gastado ARS 1.500 (150%)" in resultado
    assert "Nos pasamos en Fundaciones" in texts(at)


# --------------------------------------------------------------------------- #
# Seguridad y accesibilidad de la pantalla
# --------------------------------------------------------------------------- #
def test_f03_seg_1_texto_de_usuario_no_se_interpreta(e2e):
    """F-03-SEG-1: una descripción con Markdown no puede mostrar imágenes ni links,
    ni en la lista de gastos ni en el diálogo de anulación."""

    _obra(e2e)
    gasto = _seed_gasto(
        e2e, 100, "ARS", "Otros", tipo_cambio=1200, descripcion="![x](https://evil.test/p.png)"
    )
    at = _plata(e2e)
    crudos = "\n".join(m.value for m in at.tabs[PRESUPUESTO].markdown)
    at = at.button(key=f"gasto_anular_{gasto['id']}").click().run()
    crudos += "\n".join(m.value for m in at.markdown)

    assert "![x](https://" not in crudos
    assert r"\!\[x\]\(https\://evil\.test/p\.png\)" in crudos


def test_f03_seg_2_item_con_markdown_en_el_formulario_de_gasto(e2e):
    _obra(e2e)
    item = _item(e2e, "Otros", 10, descripcion="[link](https://evil.test)")
    at = _abrir_gasto(_plata(e2e), item["id"])
    crudos = [m.value for m in at.tabs[PRESUPUESTO].markdown] + [
        e.label for e in at.tabs[PRESUPUESTO].expander
    ]
    assert all("](https://" not in c for c in crudos)


def test_f03_a11y_1_todos_los_campos_tienen_etiqueta(e2e):
    """F-03-A11Y-1: cada campo del formulario de gasto tiene etiqueta visible y los
    obligatorios lo dicen."""

    _obra(e2e)
    item = _item(e2e, "Otros", 100)
    at = _abrir_gasto(_plata(e2e), item["id"])
    tab = at.tabs[PRESUPUESTO]
    campos = [*tab.number_input, *tab.text_input, *tab.date_input, *tab.radio, *tab.selectbox]
    propios = [c for c in campos if c.key and c.key.startswith("nuevo_gasto_")]

    assert len(propios) == 6
    for campo in propios:
        assert campo.label and campo.label.strip(), campo.key
    obligatorios = {c.key.rsplit("_", 1)[-1] for c in propios if "obligatori" in c.label}
    assert obligatorios == {"fecha", "monto", "moneda", "descripcion"}
    for b in tab.button:
        assert b.label.strip(), b.key


def test_f03_a11y_2_estado_en_palabras(e2e):
    """F-03-A11Y-2: el desvío se informa con texto, no solo con color."""

    _obra(e2e)
    item = _item(e2e, "Pintura", 100)
    _seed_gasto(e2e, 150, "ARS", "Pintura", tipo_cambio=1200, item=item)
    at = _plata(e2e)

    assert _tabla(at).loc["Pintura", "Estado"] == "Excedido"
    assert "🔴 Excedido" in texts(at)


def test_f03_seg_3_avisos_del_chat_escapan_nombres(e2e):
    """F-03-SEG-3: las propuestas del agente y los avisos de lo que guardó no
    interpretan Markdown de nombres de obra o ítem, tampoco en el historial."""

    _obra(e2e, nombre="![o](https://evil.test/o.png)")
    _item(e2e, "Otros", 100, descripcion="![r](https://evil.test/r.png)")
    at = _chat(
        e2e,
        "Cargá 10",
        tool_call(
            "registrar_gasto",
            {"monto": 10, "descripcion": "x", "item": "![r](https://evil.test/r.png)"},
        ),
        AIMessage(content="Listo."),
    )

    tarjetas = [m.value for m in at.markdown if "Propuesta, sin guardar" in m.value]
    assert tarjetas and all("](https://" not in t for t in tarjetas)
    at = confirmar_propuestas(at)
    avisos = [c.value for c in at.caption if "Gasto registrado" in c.value]
    assert avisos and all("](https://" not in a for a in avisos)
    assert len(finanzas.list_gastos(e2e.db, 1)) == 1

    at = at.run()  # siguiente carga: el aviso sale del historial de la sesión
    avisos = [c.value for c in at.caption if "Gasto registrado" in c.value]
    assert avisos and all("](https://" not in a for a in avisos)


def test_f03_seg_4_respuesta_del_agente_no_carga_imagenes(e2e):
    """F-03-SEG-4: si la respuesta del agente trae una imagen (por ejemplo, copiada
    de un dato malicioso), se muestra como texto, también en el historial."""

    _obra(e2e)
    e2e.script(AIMessage(content="Listo ![x](https://evil.test/p.png?d=datos) **ok**"))
    at = e2e.abrir_agente(e2e.login()).chat_input[0].set_value("hola").run()

    crudos = "\n".join(m.value for m in at.markdown)
    assert "\\![x](https://evil.test" in crudos and "**ok**" in crudos
    assert "Listo ![x]" not in crudos
    at = at.run()
    assert "Listo ![x]" not in "\n".join(m.value for m in at.markdown)


def test_f03_ca_27d_registrar_un_gasto_junto_a_editar_y_borrar(e2e):
    """F-03-CA-27 / #45: en la fila de cada ítem están los íconos para registrar un
    gasto, editar y borrar; el gasto se carga ahí mismo, ya vinculado al ítem, y no
    hay ningún formulario de gasto fuera de los ítems."""

    _obra(e2e)
    item = _item(e2e, "Pintura", 100, descripcion="Látex")
    at = _plata(e2e)
    acciones = [
        b.key for b in at.tabs[PRESUPUESTO].button if b.key and b.key.endswith(f"_{item['id']}")
    ]
    assert acciones == [
        f"fila_item_{item['id']}",
        f"gasto_agregar_{item['id']}",
        f"item_editar_{item['id']}",
        f"item_borrar_{item['id']}",
    ]
    assert "Registrar un gasto" not in [s.value for s in at.tabs[PRESUPUESTO].subheader]
    assert not [
        k
        for k in (w.key for w in at.tabs[PRESUPUESTO].number_input)
        if k and k.startswith("gasto_")
    ]

    at = _abrir_gasto(at, item["id"])
    assert at.button(key=f"gasto_agregar_{item['id']}").disabled  # ya está abierto
    assert "Nuevo gasto en «Látex»" in visible(at)


# --------------------------------------------------------------------------- #
# #25 · Editar un gasto
# --------------------------------------------------------------------------- #
def test_f03_ca_36_editar_gasto_muestra_sus_datos(e2e):
    """F-03-CA-36: el lápiz del gasto abre un formulario con todos sus datos actuales:
    ítem, fecha, monto, moneda, descripción, proveedor y cotización."""

    _obra(e2e)
    item = _item(e2e, "Estructura", 1_000_000, descripcion="Hierro")
    gasto = _seed_gasto(e2e, 350_000, "ARS", "", tipo_cambio=1200, item=item, descripcion="Seña")
    hierros = _proveedor(e2e, "Hierros Sur")
    e2e.db.table("gastos").update({"proveedor_id": hierros["id"]}).eq("id", gasto["id"]).execute()
    at = _plata(e2e).button(key=f"gasto_editar_{gasto['id']}").click().run()
    k = f"editar_gasto_{gasto['id']}_"

    assert at.selectbox(key=f"{k}item").value == item["id"]
    assert at.date_input(key=f"{k}fecha").value == finanzas.hoy()
    assert at.number_input(key=f"{k}monto").value == 350_000.0
    assert at.radio(key=f"{k}moneda").value == "ARS"
    assert at.text_input(key=f"{k}descripcion").value == "Seña"
    assert at.selectbox(key=f"{k}proveedor_id").value == hierros["id"]
    assert "Hierros Sur" in at.selectbox(key=f"{k}proveedor_id").options
    assert at.number_input(key=f"{k}tc").value == 1200.0
    assert "Editar el gasto «Seña»" in visible(at)


def test_f03_ca_37_guardar_cambios_y_mover_de_item(e2e):
    """F-03-CA-37: se cambian monto, descripción, fecha y se mueve el gasto a otro ítem;
    los totales del ítem y del rubro se actualizan y queda «editado»."""

    _obra(e2e)
    hierro = _item(e2e, "Estructura", 1_000_000, descripcion="Hierro")
    mesada = _item(e2e, "Carpinterías", 500_000, descripcion="Mesada")
    gasto = _seed_gasto(e2e, 350_000, "ARS", "", tipo_cambio=1200, item=hierro, descripcion="Seña")
    at = _plata(e2e).button(key=f"gasto_editar_{gasto['id']}").click().run()
    k = f"editar_gasto_{gasto['id']}_"
    at.selectbox(key=f"{k}item").set_value(mesada["id"])
    at.number_input(key=f"{k}monto").set_value(200_000.0)
    at.text_input(key=f"{k}descripcion").input("Seña mesada")
    at.date_input(key=f"{k}fecha").set_value(finanzas.hoy() - timedelta(days=1))
    at = at.button(key=f"gasto_guardar_{gasto['id']}_ed").click().run()

    assert not at.exception
    assert "Gasto actualizado: ARS 200.000" in visible(at)
    guardado = finanzas.get_gasto(e2e.db, gasto["id"])
    assert (guardado["presupuesto_item_id"], guardado["monto"], guardado["descripcion"]) == (
        mesada["id"],
        "200000.00",
        "Seña mesada",
    )
    assert guardado["fecha"] == (finanzas.hoy() - timedelta(days=1)).isoformat()
    assert _tabla(at).loc["Carpinterías", "Gastado"] == "ARS 200.000"
    assert _tabla(at).loc["Estructura", "Gastado"] == "ARS 0"


def test_f03_ca_38_cancelar_y_error_conservan(e2e):
    """F-03-CA-38: Cancelar no guarda nada; un dato inválido muestra el error y el
    formulario conserva lo escrito."""

    _obra(e2e)
    gasto = _seed_gasto(e2e, 1000, "ARS", "Pintura", tipo_cambio=1200, descripcion="Látex")
    pintureria = _proveedor(e2e, "Pinturerías X")
    at = _plata(e2e).button(key=f"gasto_editar_{gasto['id']}").click().run()
    k = f"editar_gasto_{gasto['id']}_"
    at.text_input(key=f"{k}descripcion").input("   ")
    at.selectbox(key=f"{k}proveedor_id").set_value(pintureria["id"])
    at = at.button(key=f"gasto_guardar_{gasto['id']}_ed").click().run()
    assert "No se guardaron los cambios: escribí una descripción." in visible(at)
    assert at.selectbox(key=f"{k}proveedor_id").value == pintureria["id"]

    at = at.button(key=f"gasto_cancelar_{gasto['id']}_ed").click().run()
    assert finanzas.get_gasto(e2e.db, gasto["id"])["descripcion"] == "Látex"
    assert f"{k}descripcion" not in [w.key for w in at.text_input]


def test_f03_ca_39_cambiar_fecha_recalcula_la_cotizacion(e2e):
    """F-03-CA-39: con cotización automática, cambiar la fecha del gasto la recalcula
    con el MEP de la nueva fecha."""

    hoy = finanzas.hoy()
    e2e.set_mep({hoy: (1190, 1210), hoy - timedelta(days=1): (1090, 1110)})
    _obra(e2e)
    item = _item(e2e, "Honorarios", 1000, moneda="USD")
    gasto, _ = finanzas.add_gasto(e2e.db, item["id"], monto=100, moneda="USD", descripcion="x")
    assert gasto["tipo_cambio"] == "1200.0000"
    at = _plata(e2e).button(key=f"gasto_editar_{gasto['id']}").click().run()
    at.date_input(key=f"editar_gasto_{gasto['id']}_fecha").set_value(hoy - timedelta(days=1))
    at = at.button(key=f"gasto_guardar_{gasto['id']}_ed").click().run()

    guardado = finanzas.get_gasto(e2e.db, gasto["id"])
    assert (guardado["tipo_cambio"], guardado["tipo_cambio_origen"]) == ("1100.0000", "auto")
    assert "MEP 1.100,00 (automática)" in visible(at)


def test_f03_ca_38b_cotizacion_cero_se_rechaza(e2e):
    """F-03-CA-38 (revisión PR #48): una cotización 0 al editar se rechaza con un
    mensaje claro, no guarda y el formulario conserva lo escrito."""

    _obra(e2e)
    gasto = _seed_gasto(e2e, 1000, "USD", "Honorarios", tipo_cambio=1200, descripcion="Visita")
    at = _plata(e2e).button(key=f"gasto_editar_{gasto['id']}").click().run()
    k = f"editar_gasto_{gasto['id']}_"
    at.number_input(key=f"{k}tc").set_value(0.0)
    at.text_input(key=f"{k}descripcion").input("Visita 2")
    at = at.button(key=f"gasto_guardar_{gasto['id']}_ed").click().run()

    assert "No se guardaron los cambios: El tipo de cambio tiene que ser mayor que cero." in (
        visible(at)
    )
    assert "Gasto actualizado" not in visible(at)
    guardado = finanzas.get_gasto(e2e.db, gasto["id"])
    assert (guardado["descripcion"], guardado["tipo_cambio"]) == ("Visita", "1200")
    assert at.text_input(key=f"{k}descripcion").value == "Visita 2"
