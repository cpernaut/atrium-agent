"""End-to-end flows through the real Streamlit app (external services simulated).

Each test is a user journey; the ID in the docstring matches docs/casos-e2e.md.
"""

from datetime import date

from langchain_core.messages import AIMessage

from atrium import obras
from tests.e2e.conftest import EMAIL, click, pagina_actual, texts
from tests.fakes import tool_call


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


def _obras_listadas(at) -> list[int]:
    """Ids of the obras shown in 📋 Obras, in order (one «Abrir» per card)."""

    return [
        int(b.key.rsplit("_", 1)[1]) for b in at.button if (b.key or "").startswith("abrir_obra_")
    ]


def _encabezado(at) -> str:
    """The obra activa header, always on top (#49)."""

    return "\n".join(m.value for m in at.markdown if m.value.startswith("🏗️"))


# --------------------------------------------------------------------------- #
# Acceso
# --------------------------------------------------------------------------- #
def test_e2e_01_login_con_credenciales_invalidas(e2e):
    """E2E-01: con contraseña incorrecta no entra y ve el error."""

    at = e2e.login(password="incorrecta")

    assert "No se pudo iniciar sesión" in texts(at)
    assert not at.chat_input
    assert "user" not in at.session_state


def test_e2e_02_login_valido_abre_en_la_obra_activa(e2e):
    """E2E-02 (#33, #49): con credenciales válidas entra a la obra activa (Detalle,
    Bitácora y Presupuesto), con su email en el menú y el botón del agente abajo a
    la derecha."""

    _seed(e2e.db)
    at = e2e.login()

    assert not at.exception
    assert any("Versión beta" in m.value for m in at.markdown), "falta la etiqueta beta"
    assert EMAIL in "\n".join(c.value for c in at.sidebar.caption)
    assert [t.label for t in at.tabs] == ["Detalle", "Bitácora", "Presupuesto"]
    assert "seccion" not in [r.key for r in at.radio]
    assert at.button(key="agente_abrir").label == "💬 Agente"
    assert not at.chat_input  # el chat se abre solo si se pide


def test_e2e_03_cerrar_sesion(e2e):
    """E2E-03: al cerrar sesión vuelve al login y se limpia la sesión."""

    at = click(e2e.login(), "Cerrar sesión")

    assert at.text_input(key="login_email")
    assert e2e.db.auth.signed_out == 1
    assert "user" not in at.session_state


# --------------------------------------------------------------------------- #
# Obras
# --------------------------------------------------------------------------- #
def test_e2e_04_crear_obra(e2e):
    """E2E-04: crea una obra desde «Nueva obra»; queda como obra activa y aparece
    en el listado de Obras."""

    at = e2e.login()  # sin obras, la app abre en «Nueva obra» (#49 D8)
    assert pagina_actual(at) == "Nueva obra"
    assert "Te damos la bienvenida" in texts(at)

    at.text_input(key="nueva_nombre").input("Casa Lote 12")
    at.text_input(key="nueva_cliente").input("Pérez")
    at.selectbox(key="nueva_municipio").set_value("La Plata")
    at.selectbox(key="nueva_estado").set_value("En curso")
    at.number_input(key="nueva_presupuesto").set_value(85000.0)
    at.selectbox(key="nueva_moneda").set_value("USD")
    at = click(at, "Crear obra")

    assert not at.exception
    assert "Obra «Casa Lote 12» creada: es la obra activa." in texts(at)
    assert at.selectbox(key="obra_elegida").value == 1  # queda como obra activa
    assert pagina_actual(at) == "Detalle"  # y se abre su detalle
    guardada = obras.find_obras(e2e.db, "Lote 12")[0]
    assert guardada["municipio"] == "La Plata" and guardada["moneda"] == "USD"
    assert guardada["presupuesto"] == 85000.0 and guardada["estado"] == "En curso"

    at = e2e.ir_a(at, "obras")  # figura en el listado y en las métricas
    assert _obras_listadas(at) == [1]
    assert [m.value for m in at.metric] == ["1", "1", "0%"]


def test_e2e_05_obra_sin_nombre(e2e):
    """E2E-05: no deja crear una obra sin nombre."""

    at = click(e2e.login(), "Crear obra")

    assert "La obra necesita un nombre." in texts(at)
    assert obras.list_obras(e2e.db) == []


def test_e2e_06_actualizar_estado_y_avance(e2e):
    """E2E-06: cambia estado y avance de una obra desde su Detalle."""

    _seed(e2e.db)
    at = e2e.elegir_obra(e2e.login(), 1)
    at.selectbox(key="det_estado_1").set_value("Pausada")
    at.slider(key="det_avance_1").set_value(55)
    at = click(at, "Guardar cambios")

    assert not at.exception
    obra = obras.get_obra(e2e.db, 1)
    assert (obra["estado"], obra["avance"]) == ("Pausada", 55)
    assert obras.get_obra(e2e.db, 2)["avance"] == 0  # la otra obra no se tocó


def test_e2e_07_filtrar_por_estado(e2e):
    """E2E-07: el filtro por estado deja solo las obras de ese estado."""

    _seed(e2e.db)
    at = e2e.ir_a(e2e.login(), "obras")
    assert sorted(_obras_listadas(at)) == [1, 2]

    at = at.multiselect(key="lista_filtro").set_value(["En curso"]).run()

    assert _obras_listadas(at) == [1]


def test_e2e_08_bitacora_manual(e2e):
    """E2E-08: agrega una nota en la bitácora con autor y fecha, y la muestra."""

    _seed(e2e.db)
    at = e2e.go_to_obras(e2e.login())
    at = e2e.elegir_obra(at, 1)
    at.date_input(key="nota_fecha").set_value(date(2026, 10, 20))
    at.text_area(key="nota_texto").input("Hormigonado de platea")
    at = click(at, "Agregar nota")

    assert not at.exception
    nota = obras.list_bitacora(e2e.db, 1)[0]
    assert (nota["nota"], nota["autor"], nota["fecha"]) == (
        "Hormigonado de platea",
        EMAIL,
        "2026-10-20",
    )
    assert "Hormigonado de platea" in texts(at)


def test_e2e_09_bitacora_nota_vacia(e2e):
    """E2E-09: una nota vacía no se guarda."""

    _seed(e2e.db)
    at = e2e.go_to_obras(e2e.login())
    at.text_area(key="nota_texto").input("   ")
    at = click(at, "Agregar nota")

    assert "La nota está vacía." in texts(at)
    assert obras.list_bitacora(e2e.db, 1) == []


def test_e2e_10_tablas_faltantes(e2e):
    """E2E-10: si faltan las tablas, Obras explica qué hacer en vez de romperse."""

    at = e2e.login()
    e2e.db.fail = 'relation "public.obras" does not exist'
    at = e2e.go_to_obras(at)

    assert not at.exception
    assert "supabase_schema.sql" in texts(at)


# --------------------------------------------------------------------------- #
# Agente + obras
# --------------------------------------------------------------------------- #
def test_e2e_11_normativa_de_la_obra_activa(e2e):
    """E2E-11: con obra activa, el agente busca solo en el código de su municipio."""

    _seed(e2e.db)
    e2e.script(AIMessage(content="Para Casa Lote 12 el retiro de frente es de 3 m."))
    at = e2e.login()
    at = e2e.elegir_obra(at, 1)
    at = e2e.abrir_agente(at).chat_input[0].set_value("¿Qué retiro de frente necesito?").run()

    assert not at.exception
    assert e2e.store.filters == [{"source": "Codigo Edificacion de La Plata.pdf"}]
    prompt = e2e.llm.seen[0][0].content
    assert "Casa Lote 12" in prompt and "código de edificación de La Plata" in prompt
    assert "el retiro de frente es de 3 m" in texts(at)


def test_e2e_12_sin_obra_activa_busca_en_todo(e2e):
    """E2E-12: sin obras cargadas, el agente responde normativa sin filtrar."""

    e2e.script(AIMessage(content="Depende del municipio."))
    at = e2e.abrir_agente(e2e.login()).chat_input[0].set_value("¿Altura máxima permitida?").run()

    assert not at.exception
    assert e2e.store.filters == [None]
    assert "No hay una obra activa" in e2e.llm.seen[0][0].content


def test_e2e_13_consultar_obras_por_chat(e2e):
    """E2E-13: «¿qué obras tengo en curso?» responde con datos del tracker."""

    _seed(e2e.db)
    e2e.script(
        tool_call("listar_obras", {"estado": "En curso"}),
        AIMessage(content="Tenés 1 obra en curso: Casa Lote 12 (30%)."),
    )
    at = e2e.abrir_agente(e2e.login()).chat_input[0].set_value("¿Qué obras tengo en curso?").run()

    assert not at.exception
    resultado_herramienta = e2e.llm.seen[1][-1].content
    assert "Casa Lote 12" in resultado_herramienta and "Hudson" not in resultado_herramienta
    assert "Tenés 1 obra en curso" in texts(at)


def test_e2e_14_cargar_avance_y_nota_por_chat(e2e):
    """E2E-14: pedido por chat -> nota + avance guardados, avisos visibles y
    los cambios se ven después en la obra activa."""

    _seed(e2e.db)
    e2e.script(
        tool_call("agregar_nota_bitacora", {"nota": "Hormigonado de platea"}, "c1"),
        tool_call("actualizar_obra", {"avance": 40}, "c2"),
        AIMessage(content="Listo: anoté la nota y pasé el avance a 40%."),
    )
    at = e2e.login()
    at = e2e.elegir_obra(at, 1)
    at = (
        e2e.abrir_agente(at)
        .chat_input[0]
        .set_value("Anotá que se hormigonó la platea y pasá el avance a 40%")
        .run()
    )

    assert not at.exception
    pantalla = texts(at)
    assert "📝 Nota agregada a la bitácora de «Casa Lote 12»" in pantalla
    assert "✏️ «Casa Lote 12» actualizada: avance → 40%" in pantalla
    assert obras.list_bitacora(e2e.db, 1)[0]["autor"] == EMAIL

    at = e2e.go_to_obras(at)
    assert "Casa Lote 12** · En curso · 40 % de avance" in _encabezado(at)
    assert at.slider(key="det_avance_1").value == 40
    assert "Hormigonado de platea" in texts(at)


def test_e2e_15_obra_ambigua_no_escribe(e2e):
    """E2E-15: si la obra pedida es ambigua, no escribe nada y pide aclarar."""

    _seed(e2e.db)
    obras.create_obra(e2e.db, {"nombre": "Casa Lote 14"})
    e2e.script(
        tool_call("agregar_nota_bitacora", {"nota": "Llegó el hierro", "obra": "Casa Lote"}),
        AIMessage(content="¿En cuál obra? Casa Lote 12 o Casa Lote 14."),
    )
    at = (
        e2e.abrir_agente(e2e.login())
        .chat_input[0]
        .set_value("Anotá en Casa Lote que llegó el hierro")
        .run()
    )

    assert not at.exception
    assert "varias obras" in e2e.llm.seen[1][-1].content
    assert all(obras.list_bitacora(e2e.db, i) == [] for i in (1, 3))
    assert "📝" not in texts(at)


def test_e2e_16_historial_se_guarda(e2e):
    """E2E-16: pregunta y respuesta quedan en la tabla de historial del usuario."""

    e2e.script(AIMessage(content="La altura máxima es de 9 m."))
    e2e.abrir_agente(e2e.login()).chat_input[0].set_value("¿Altura máxima?").run()

    filas = e2e.db.tables["mensajes"]
    assert [(f["rol"], f["contenido"]) for f in filas] == [
        ("user", "¿Altura máxima?"),
        ("assistant", "La altura máxima es de 9 m."),
    ]
    assert {f["user_id"] for f in filas} == {f"id-{EMAIL}"}


def test_e2e_17_login_y_app_muestran_el_logo(e2e, monkeypatch):
    """E2E-17: el login muestra el logo de Atrium; la app usa el isotipo como favicon
    y el logo arriba a la izquierda."""

    import streamlit

    llamadas = {}
    real_config, real_logo = streamlit.set_page_config, streamlit.logo

    def config(**kwargs):
        llamadas["config"] = kwargs
        return real_config(**kwargs)

    def logo(image, **kwargs):
        llamadas["logo"] = (image, kwargs)
        return real_logo(image, **kwargs)

    monkeypatch.setattr(streamlit, "set_page_config", config)
    monkeypatch.setattr(streamlit, "logo", logo)

    at = e2e.open()

    assert not at.exception
    assert "Atrium Studio" in [x.value for x in at.title]
    assert any("Versión beta" in m.value for m in at.markdown)
    assert llamadas["config"]["page_title"] == "Atrium Studio · Beta"
    logos = [m.value for m in at.markdown if 'alt="Atrium Studio"' in m.value]
    assert logos and "data:image/svg+xml;base64," in logos[0], "el login no muestra el logo"
    assert llamadas["config"]["page_icon"].endswith("assets/favicon.png")
    imagen, opciones = llamadas["logo"]
    assert imagen.endswith("assets/atrium-favicon.svg")
    assert opciones["icon_image"].endswith("assets/atrium-favicon.svg")


def test_e2e_18_historial_interrumpido_se_recupera(e2e):
    """E2E-18: si la carga del historial se corta a mitad de camino (por ejemplo, un
    toque que dispara otra recarga), la app no queda rota: vuelve a cargarlo."""

    e2e.db.table("mensajes").insert(
        {"user_id": f"id-{EMAIL}", "thread_id": "t", "rol": "user", "contenido": "Hola de ayer"}
    ).execute()
    at = e2e.login()
    # Sesión como la que dejó el error: conversación iniciada pero sin historial.
    del at.session_state["history"]
    at = e2e.abrir_agente(at.run())

    assert not at.exception
    assert any("Hola de ayer" in m.value for m in at.markdown)


# --------------------------------------------------------------------------- #
# Una sola obra elegida (UX-02, issue #7) y agente flotante (#33)
# --------------------------------------------------------------------------- #
def test_ux_02_ca_1_una_obra_para_toda_la_app(e2e):
    """UX-02-CA-1: la obra que se elige en el menú es la de todas las pestañas y la
    del agente; no hay otros selectores de obra."""

    _seed(e2e.db)
    obras.add_nota(e2e.db, 2, "Nota de Hudson", autor=EMAIL)
    e2e.script(AIMessage(content="Listo."))
    at = e2e.elegir_obra(e2e.login(), 2)

    claves = [w.key for w in at.selectbox]
    assert claves.count("obra_elegida") == 1
    assert not {"lista_obra", "bitacora_obra", "plata_obra"} & set(claves)
    assert [w.key for w in at.sidebar.selectbox] == ["obra_elegida"]  # en el menú (#49)
    assert at.text_input(key="det_nombre_2").value == "Ampliación Hudson"  # Detalle
    assert "Nota de Hudson" in texts(at)  # Bitácora de la misma obra
    assert at.button(key="item_agregar")  # Presupuesto de la misma obra, sin otro selector

    at = e2e.abrir_agente(at)
    assert "Trabajando sobre **Ampliación Hudson**" in [c.value for c in at.caption]
    at.chat_input(key="agente_input").set_value("¿Qué retiro pide el código?").run()
    assert e2e.store.filters == [{"source": "codigo-edificacion-berazategui.pdf"}]


def test_ux_02_ca_2_por_defecto_nunca_una_terminada(e2e):
    """UX-02-CA-2: al entrar, si hay una obra En curso, no se elige una Terminada o
    Cancelada aunque sea la más nueva."""

    obras.create_obra(e2e.db, {"nombre": "Vieja en curso", "estado": "En curso"})
    obras.create_obra(e2e.db, {"nombre": "Nueva terminada", "estado": "Terminada"})
    obras.create_obra(e2e.db, {"nombre": "Nueva cancelada", "estado": "Cancelada"})
    at = e2e.login()

    assert at.selectbox(key="obra_elegida").value == 1
    opciones = at.selectbox(key="obra_elegida").options
    assert opciones[0] == "Vieja en curso · En curso"  # las activas primero
    assert opciones[-1].endswith("· Cancelada")


def test_ux_02_ca_3_la_eleccion_se_mantiene(e2e):
    """UX-02-CA-3: la obra elegida se mantiene al cambiar de pestaña, abrir el
    agente y recargar."""

    _seed(e2e.db)
    at = e2e.elegir_obra(e2e.login(), 2)
    at = e2e.abrir_agente(at).run()
    assert at.selectbox(key="obra_elegida").value == 2
    at = at.button(key="agente_cerrar").click().run()
    assert at.selectbox(key="obra_elegida").value == 2


def test_agente_flotante_se_abre_y_se_cierra(e2e):
    """AGENTE-1 (#33): el agente es un botón abajo a la derecha; se abre con el chat
    y la obra sobre la que trabaja, y se cierra sin perder la conversación."""

    _seed(e2e.db)
    e2e.script(AIMessage(content="La altura máxima es de 9 m."))
    at = e2e.login()
    assert not at.chat_input

    at = e2e.abrir_agente(at)
    assert at.chat_input(key="agente_input")
    assert at.button(key="agente_cerrar").label == "✕ Cerrar"
    assert any("Probá con" in c.value for c in at.caption)  # ayuda para empezar
    at = at.chat_input(key="agente_input").set_value("¿Altura máxima?").run()
    assert "La altura máxima es de 9 m." in texts(at)

    at = at.button(key="agente_cerrar").click().run()
    assert not at.chat_input and at.button(key="agente_abrir")
    at = e2e.abrir_agente(at)
    assert "La altura máxima es de 9 m." in texts(at)  # la conversación sigue ahí


def test_agente_flotante_actualiza_la_pantalla(e2e):
    """AGENTE-2: si el agente cambia datos (avance, notas, gastos), la pantalla de
    atrás se recarga y los muestra sin tocar nada más."""

    _seed(e2e.db)
    e2e.script(
        tool_call("actualizar_obra", {"avance": 70}, "c1"),
        AIMessage(content="Avance en 70%."),
    )
    at = e2e.abrir_agente(e2e.elegir_obra(e2e.login(), 1))
    at = at.chat_input(key="agente_input").set_value("Pasá el avance a 70").run()

    assert "70 % de avance" in _encabezado(at)
    assert at.slider(key="det_avance_1").value == 70
    assert "Avance en 70%." in texts(at)


def test_agente_2b_el_formulario_no_pisa_lo_que_cargo_el_agente(e2e):
    """AGENTE-2 (revisión PR #43): si el agente cambia el avance y después se guarda
    el estado desde el Detalle, el avance nuevo se conserva."""

    _seed(e2e.db)
    e2e.script(
        tool_call("actualizar_obra", {"avance": 70}, "c1"),
        AIMessage(content="Avance en 70%."),
    )
    at = e2e.elegir_obra(e2e.login(), 1)
    assert at.slider(key="det_avance_1").value == 30
    at = e2e.abrir_agente(at).chat_input(key="agente_input").set_value("Pasá el avance a 70").run()

    assert at.slider(key="det_avance_1").value == 70  # el formulario muestra el dato nuevo
    at.selectbox(key="det_estado_1").set_value("Pausada")
    at = click(at, "Guardar cambios")
    obra = obras.get_obra(e2e.db, 1)
    assert (obra["estado"], obra["avance"]) == ("Pausada", 70)


def test_agente_3_una_pregunta_no_escribe(e2e):
    """AGENTE-3 (#51): si el usuario solo pregunta («¿cómo viene el avance?»), el agente
    no cambia nada aunque el modelo intente actualizar la obra o anotar algo."""

    _seed(e2e.db)
    e2e.script(
        tool_call("actualizar_obra", {"avance": 99}, "c1"),
        tool_call("agregar_nota_bitacora", {"nota": "x"}, "c2"),
        AIMessage(content="Viene al 30%."),
    )
    at = e2e.abrir_agente(e2e.elegir_obra(e2e.login(), 1))
    at = at.chat_input(key="agente_input").set_value("¿Cómo viene el avance?").run()

    assert not at.exception
    resultados = [m.content for m in e2e.llm.seen[-1] if m.type == "tool"]
    assert all(r.startswith("No ") for r in resultados)
    assert obras.get_obra(e2e.db, 1)["avance"] == 30
    assert obras.list_bitacora(e2e.db, 1) == []


def test_agente_3b_pregunta_con_verbo_no_escribe(e2e):
    """AGENTE-3b (#51): una pregunta sobre algo hecho («¿se cargó el gasto?», «¿anotaron
    algo?») no autoriza escribir aunque el modelo lo intente."""

    _seed(e2e.db)
    e2e.script(
        tool_call("agregar_nota_bitacora", {"nota": "x"}, "c1"),
        AIMessage(content="No hay notas nuevas."),
        tool_call("agregar_nota_bitacora", {"nota": "y"}, "c2"),
        AIMessage(content="Ok."),
    )
    at = e2e.abrir_agente(e2e.elegir_obra(e2e.login(), 1))
    at = at.chat_input(key="agente_input").set_value("¿Se anotó algo de la platea?").run()
    at = at.chat_input(key="agente_input").set_value("Ya cargué la seña ayer").run()

    assert not at.exception
    assert obras.list_bitacora(e2e.db, 1) == []


def test_agente_3c_cada_pedido_autoriza_solo_su_accion(e2e):
    """AGENTE-3c (#51): «cambiá el avance a 50; no registres ese gasto» deja actualizar
    la obra pero no registrar el gasto, aunque el modelo lo intente."""

    _seed(e2e.db)
    e2e.script(
        tool_call("actualizar_obra", {"avance": 50}, "c1"),
        tool_call(
            "registrar_gasto", {"monto": 10, "descripcion": "x", "item": "imprevistos"}, "c2"
        ),
        AIMessage(content="Avance en 50%."),
    )
    at = e2e.abrir_agente(e2e.elegir_obra(e2e.login(), 1))
    at = (
        at.chat_input(key="agente_input")
        .set_value("Cambiá el avance a 50; no registres ese gasto")
        .run()
    )

    assert not at.exception
    assert obras.get_obra(e2e.db, 1)["avance"] == 50
    resultados = [m.content for m in e2e.llm.seen[-1] if m.type == "tool"]
    assert resultados[1].startswith("No registré")
