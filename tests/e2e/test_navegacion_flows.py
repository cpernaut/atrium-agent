"""#49 · UX-03: left menu, obra activa always visible and its editable Detalle.

Each test is a user journey; the ID in the docstring matches docs/casos-e2e.md.
"""

from datetime import date

from langchain_core.messages import AIMessage

from atrium import finanzas, obras
from tests.e2e.conftest import EMAIL, click, pagina_actual, texts

PANTALLAS = ["obra", "obras", "nueva-obra", "rubros", "proveedores"]


def _seed(db):
    obras.create_obra(
        db,
        {
            "nombre": "Casa Lote 12",
            "cliente": "Pérez",
            "municipio": "La Plata",
            "estado": "En curso",
            "avance": 30,
        },
    )
    obras.create_obra(db, {"nombre": "Ampliación Hudson", "municipio": "Berazategui"})


def _encabezado(at) -> str:
    return "\n".join(m.value for m in at.markdown if m.value.startswith("🏗️"))


def _menu(at) -> list[str]:
    """Screens of the left menu (url paths), as Streamlit registered them."""

    return [
        info.get("url_pathname") or info.get("page_name") for info in at._registered_pages.values()
    ]


def test_ux_03_ca_1_menu_izquierdo(e2e):
    """UX-03-CA-1: el menú de la izquierda tiene el selector de obra activa y las
    pantallas Obra activa, Obras, Nueva obra, Rubros y Proveedores."""

    _seed(e2e.db)
    at = e2e.login()

    assert not at.exception
    assert [w.label for w in at.sidebar.selectbox] == ["Obra activa"]
    assert at.sidebar.selectbox(key="obra_elegida").value == 1
    assert set(_menu(at)) >= {"obras", "nueva-obra", "rubros", "proveedores"}
    assert len(_menu(at)) == 5  # la quinta es «Obra activa», la pantalla de inicio


def test_ux_03_ca_2_obra_activa_siempre_visible(e2e):
    """UX-03-CA-2: en todas las pantallas, arriba, se ve la obra activa con su estado
    y su avance."""

    _seed(e2e.db)
    at = e2e.login()
    for pantalla in PANTALLAS:
        at = e2e.ir_a(at, pantalla)
        assert not at.exception, pantalla
        assert "🏗️ **Casa Lote 12** · En curso · 30 % de avance" in _encabezado(at), pantalla

    at = e2e.elegir_obra(at, 2)
    assert "**Ampliación Hudson** · Planificación · 0 % de avance" in _encabezado(at)


def test_ux_03_ca_3_detalle_bitacora_y_presupuesto(e2e):
    """UX-03-CA-3: la obra activa se ve en tres pestañas, Detalle, Bitácora y
    Presupuesto; «Plata» ya no aparece en ninguna pantalla."""

    _seed(e2e.db)
    at = e2e.login()

    assert [t.label for t in at.tabs] == ["Detalle", "Bitácora", "Presupuesto"]
    assert at.text_input(key="det_nombre_1").value == "Casa Lote 12"
    assert at.button(key="item_agregar")  # el presupuesto de la obra
    for pantalla in PANTALLAS:
        at = e2e.ir_a(at, pantalla)
        assert "Plata" not in texts(at).replace("La Plata", ""), pantalla
        assert "💰" not in [t.label for t in at.tabs]


def test_ux_03_ca_4_editar_todos_los_datos(e2e):
    """UX-03-CA-4: en Detalle se editan y guardan todos los datos de la obra; solo se
    envía lo que cambió y la otra obra no se toca."""

    _seed(e2e.db)
    at = e2e.login()
    at.text_input(key="det_nombre_1").input("Casa Lote 12 bis")
    at.text_input(key="det_cliente_1").input("Gómez")
    at.text_input(key="det_responsable_1").input("Caro")
    at.text_input(key="det_direccion_1").input("Calle 5 n.º 1234")
    at.selectbox(key="det_municipio_1").set_value("Berazategui")
    at.selectbox(key="det_tipo_1").set_value("Reforma")
    at.selectbox(key="det_estado_1").set_value("Pausada")
    at.slider(key="det_avance_1").set_value(45)
    at.date_input(key="det_fecha_inicio_1").set_value(date(2026, 9, 1))
    at.date_input(key="det_fecha_fin_estimada_1").set_value(date(2027, 3, 1))
    at.number_input(key="det_presupuesto_1").set_value(37000.0)
    at.selectbox(key="det_moneda_1").set_value("USD")
    at = click(at, "Guardar cambios")

    assert not at.exception
    assert "Obra actualizada." in texts(at)
    obra = obras.get_obra(e2e.db, 1)
    assert {k: obra[k] for k in obras.CAMPOS_EDITABLES_OBRA} == {
        "nombre": "Casa Lote 12 bis",
        "cliente": "Gómez",
        "responsable": "Caro",
        "direccion": "Calle 5 n.º 1234",
        "municipio": "Berazategui",
        "tipo": "Reforma",
        "estado": "Pausada",
        "avance": 45,
        "fecha_inicio": "2026-09-01",
        "fecha_fin_estimada": "2027-03-01",
        "presupuesto": 37000.0,
        "moneda": "USD",
    }
    assert "Casa Lote 12 bis** · Pausada · 45 % de avance" in _encabezado(at)
    assert obras.get_obra(e2e.db, 2)["nombre"] == "Ampliación Hudson"


def test_ux_03_ca_4b_sin_cambios_no_escribe(e2e):
    """UX-03-CA-4b: guardar sin haber cambiado nada avisa que no hay cambios y no
    escribe en la base."""

    _seed(e2e.db)
    antes = dict(obras.get_obra(e2e.db, 1))
    at = click(e2e.login(), "Guardar cambios")

    assert "No hay cambios para guardar." in texts(at)
    assert obras.get_obra(e2e.db, 1) == antes


def test_ux_03_ca_5_error_conserva_lo_escrito(e2e):
    """UX-03-CA-5: si el guardado falla (nombre vacío), dice por qué, no guarda nada
    y el formulario conserva lo escrito."""

    _seed(e2e.db)
    at = e2e.login()
    at.text_input(key="det_nombre_1").input("   ")
    at.text_input(key="det_cliente_1").input("Gómez")
    at = click(at, "Guardar cambios")

    assert "La obra necesita un nombre." in texts(at)
    assert obras.get_obra(e2e.db, 1)["cliente"] == "Pérez"
    assert at.text_input(key="det_cliente_1").value == "Gómez"


def test_ux_03_ca_6_descartar_vuelve_a_lo_guardado(e2e):
    """UX-03-CA-6: «Descartar cambios» vuelve el formulario a los datos guardados sin
    escribir nada."""

    _seed(e2e.db)
    at = e2e.login()
    at.text_input(key="det_cliente_1").input("Gómez")
    at.slider(key="det_avance_1").set_value(90)
    at = click(at, "Descartar cambios")

    assert at.text_input(key="det_cliente_1").value == "Pérez"
    assert at.slider(key="det_avance_1").value == 30
    assert obras.get_obra(e2e.db, 1)["avance"] == 30


def test_ux_03_ca_7_abrir_una_obra_del_listado(e2e):
    """UX-03-CA-7: en Obras, «Abrir» deja esa obra como activa y muestra su detalle."""

    _seed(e2e.db)
    at = e2e.ir_a(e2e.login(), "obras")
    assert pagina_actual(at) == "Obras"
    assert "Obra activa" in texts(at)  # marca cuál es la activa, en palabras

    at = at.button(key="abrir_obra_2").click().run()

    assert not at.exception
    assert pagina_actual(at) == "Detalle"
    assert at.selectbox(key="obra_elegida").value == 2
    assert at.text_input(key="det_nombre_2").value == "Ampliación Hudson"


def test_ux_03_ca_8_la_obra_activa_se_recuerda(e2e):
    """UX-03-CA-8: al volver a entrar (otra sesión u otro dispositivo) la obra activa
    es la última que eligió ese usuario."""

    _seed(e2e.db)
    at = e2e.elegir_obra(e2e.login(), 2)
    assert e2e.db.auth.metadata[EMAIL]["obra_activa"] == 2
    at = click(at, "Cerrar sesión")

    otra = e2e.login()  # sesión nueva, como desde el celular
    assert otra.selectbox(key="obra_elegida").value == 2
    assert "**Ampliación Hudson**" in _encabezado(otra)


def test_ux_03_ca_8b_solo_guarda_cuando_cambia(e2e):
    """UX-03-CA-8b: la obra activa se guarda en la cuenta solo cuando cambia, no en
    cada recarga."""

    _seed(e2e.db)
    at = e2e.login()
    at = e2e.ir_a(e2e.ir_a(at, "obras"), "obra")
    at = e2e.elegir_obra(at, 2)
    at = e2e.elegir_obra(at, 2).run()

    assert e2e.db.auth.updates == [{"data": {"obra_activa": 1}}, {"data": {"obra_activa": 2}}]


def test_ux_03_ca_8c_obra_guardada_que_ya_no_existe(e2e):
    """UX-03-CA-8c: si la obra recordada ya no existe (o el dato es inválido), entra
    a la En curso más nueva."""

    _seed(e2e.db)
    e2e.db.auth.metadata[EMAIL]["obra_activa"] = 99
    assert e2e.login().selectbox(key="obra_elegida").value == 1
    e2e.db.auth.metadata[EMAIL]["obra_activa"] = "<script>"
    assert e2e.login().selectbox(key="obra_elegida").value == 1


def test_ux_03_ca_8d_si_no_se_puede_recordar_sigue_andando(e2e):
    """UX-03-CA-8d: si no se puede guardar la obra activa en la cuenta, la app sigue
    funcionando con la obra elegida."""

    _seed(e2e.db)
    e2e.db.auth.falla_update = True
    at = e2e.elegir_obra(e2e.login(), 2)

    assert not at.exception
    assert at.text_input(key="det_nombre_2").value == "Ampliación Hudson"
    assert e2e.db.auth.metadata[EMAIL] == {}


def test_ux_03_ca_9_obra_nueva_queda_activa(e2e):
    """UX-03-CA-9: al crear una obra desde «Nueva obra», queda como obra activa y se
    abre su detalle."""

    _seed(e2e.db)
    at = e2e.ir_a(e2e.login(), "nueva-obra")
    assert "Te damos la bienvenida" not in texts(at)  # solo cuando no hay obras
    at.text_input(key="nueva_nombre").input("Casa Haras")
    at = click(at, "Crear obra")

    assert not at.exception
    assert pagina_actual(at) == "Detalle"
    assert at.selectbox(key="obra_elegida").value == 3
    assert "**Casa Haras**" in _encabezado(at)
    assert e2e.db.auth.metadata[EMAIL]["obra_activa"] == 3


def test_ux_03_ca_10_sin_obras_abre_nueva_obra(e2e):
    """UX-03-CA-10: sin obras cargadas, la app abre en «Nueva obra» con un mensaje de
    bienvenida, también si se toca «Obra activa»."""

    at = e2e.login()
    assert pagina_actual(at) == "Nueva obra"
    assert "Te damos la bienvenida a Atrium Studio" in texts(at)
    assert "Sin obra activa" in _encabezado(at)

    at = e2e.ir_a(at, "obra")
    assert pagina_actual(at) == "Nueva obra"


def test_ux_03_ca_11_agente_sobre_la_obra_activa(e2e):
    """UX-03-CA-11: el agente trabaja sobre la obra activa, en cualquier pantalla."""

    _seed(e2e.db)
    e2e.script(AIMessage(content="Listo."))
    at = e2e.ir_a(e2e.elegir_obra(e2e.login(), 2), "rubros")
    at = e2e.abrir_agente(at)

    assert "Trabajando sobre **Ampliación Hudson**" in [c.value for c in at.caption]
    at.chat_input(key="agente_input").set_value("¿Qué retiro pide el código?").run()
    assert e2e.store.filters == [{"source": "codigo-edificacion-berazategui.pdf"}]


def test_ux_03_ca_12_municipio_nuevo_cambia_la_normativa(e2e):
    """UX-03-CA-12 (D6): si se cambia el municipio en Detalle, el agente pasa a usar
    la normativa del municipio nuevo."""

    _seed(e2e.db)
    e2e.script(AIMessage(content="Listo."))
    at = e2e.login()
    at.selectbox(key="det_municipio_1").set_value("Berazategui")
    at = click(at, "Guardar cambios")
    at = e2e.abrir_agente(at)
    at.chat_input(key="agente_input").set_value("¿Retiro de frente?").run()

    assert e2e.store.filters == [{"source": "codigo-edificacion-berazategui.pdf"}]


def test_ux_03_ca_13_presupuesto_no_recalcula_imprevistos(e2e):
    """UX-03-CA-13 (D5): cambiar el presupuesto de la obra no recalcula su ítem
    «Imprevistos»."""

    _seed(e2e.db)
    item, _ = finanzas.crear_imprevistos(e2e.db, obras.get_obra(e2e.db, 1))
    at = e2e.login()
    at.number_input(key="det_presupuesto_1").set_value(500000.0)
    at = click(at, "Guardar cambios")

    assert obras.get_obra(e2e.db, 1)["presupuesto"] == 500000.0
    assert finanzas.list_presupuesto(e2e.db, 1)[0]["monto"] == item["monto"]


def test_ux_03_ca_14_texto_de_usuario_no_se_interpreta(e2e):
    """UX-03-CA-14: un nombre de obra con Markdown se muestra como texto en el
    encabezado y en el listado (no carga imágenes ni links)."""

    obras.create_obra(e2e.db, {"nombre": "![x](https://evil.test/a.png) **Obra**"})
    at = e2e.login()
    crudos = [m.value for m in at.markdown]
    assert not any("](https://evil.test" in c and "\\]" not in c for c in crudos)
    at = e2e.ir_a(at, "obras")
    assert not any("](https://evil.test" in m.value and "\\]" not in m.value for m in at.markdown)


def test_ux_03_ca_15_rubros_agregar_ordenar_y_desactivar(e2e):
    """UX-03-CA-15: en Rubros se agrega un rubro, se sube un lugar y se desactiva y
    reactiva; «Otros» no se puede desactivar."""

    at = e2e.ir_a(e2e.login(), "rubros")
    assert pagina_actual(at) == "Rubros"

    at.text_input(key="rubro_nuevo_nombre").input("Piscina")
    at = click(at, "Agregar rubro")
    assert "Rubro «Piscina» agregado." in texts(at)
    assert at.text_input(key="rubro_nuevo_nombre").value == ""
    piscina = finanzas.find_rubros(e2e.db, "Piscina")[0]
    nombres = [r["nombre"] for r in finanzas.list_rubros(e2e.db)]
    anterior = nombres[nombres.index("Piscina") - 1]

    at = at.button(key=f"rubro_subir_{piscina['id']}").click().run()
    nombres = [r["nombre"] for r in finanzas.list_rubros(e2e.db)]
    assert nombres.index("Piscina") + 1 == nombres.index(anterior)

    at = at.button(key=f"rubro_activo_{piscina['id']}").click().run()
    assert "Rubro «Piscina» desactivado." in texts(at)
    assert "Piscina" not in [r["nombre"] for r in finanzas.list_rubros(e2e.db)]
    assert at.button(key=f"rubro_activo_{piscina['id']}").label == "Reactivar"
    at = at.button(key=f"rubro_activo_{piscina['id']}").click().run()
    assert "Piscina" in [r["nombre"] for r in finanzas.list_rubros(e2e.db)]

    otros = finanzas.find_rubros(e2e.db, "Otros")[0]
    at = at.button(key=f"rubro_activo_{otros['id']}").click().run()
    assert "«Otros» no se puede desactivar" in texts(at)
    assert finanzas.find_rubros(e2e.db, "Otros")


def test_ux_03_ca_15b_rubro_duplicado_conserva_lo_escrito(e2e):
    """UX-03-CA-15b: un rubro repetido no se agrega; dice por qué y conserva lo
    escrito."""

    at = e2e.ir_a(e2e.login(), "rubros")
    at.text_input(key="rubro_nuevo_nombre").input("ESTRUCTURA")
    at = click(at, "Agregar rubro")

    assert "Ya existe el rubro «Estructura»" in texts(at)
    assert at.text_input(key="rubro_nuevo_nombre").value == "ESTRUCTURA"


def test_ux_03_ca_16_proveedores(e2e):
    """UX-03-CA-16: Proveedores abre la lista compartida (antes decía «Próximamente»;
    ahora es F-06)."""

    at = e2e.ir_a(e2e.login(), "proveedores")

    assert pagina_actual(at) == "Proveedores"
    assert "Todavía no hay proveedores" in texts(at)


def test_ux_03_ca_4c_no_pisa_cambios_de_otro_usuario(e2e):
    """UX-03-CA-4c (R4): si otro usuario cambia el avance mientras edito solo el
    cliente, al guardar se envía solo el cliente y su avance se conserva."""

    _seed(e2e.db)
    at = e2e.login()
    at.text_input(key="det_cliente_1").input("Gómez")
    obras.update_obra(e2e.db, 1, {"avance": 60})  # otro usuario, mientras tanto
    at = click(at, "Guardar cambios")

    obra = obras.get_obra(e2e.db, 1)
    assert (obra["cliente"], obra["avance"]) == ("Gómez", 60)
