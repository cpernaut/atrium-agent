"""End-to-end flows through the real Streamlit app (external services simulated).

Each test is a user journey; the ID in the docstring matches docs/casos-e2e.md.
"""

from datetime import date

from langchain_core.messages import AIMessage

from atrium import obras
from tests.e2e.conftest import EMAIL, click, texts
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


# --------------------------------------------------------------------------- #
# Acceso
# --------------------------------------------------------------------------- #
def test_e2e_01_login_con_credenciales_invalidas(e2e):
    """E2E-01: con contraseña incorrecta no entra y ve el error."""

    at = e2e.login(password="incorrecta")

    assert "No se pudo iniciar sesión" in texts(at)
    assert not at.chat_input
    assert "user" not in at.session_state


def test_e2e_02_login_valido_muestra_agente(e2e):
    """E2E-02: con credenciales válidas ve el agente, su email y el chat."""

    at = e2e.login()

    assert not at.exception
    assert "🏗️ Atrium Agent" in texts(at)
    assert EMAIL in "\n".join(m.value for m in at.sidebar.markdown)
    assert at.chat_input


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
    """E2E-04: crea una obra desde el formulario y aparece en el listado."""

    at = e2e.go_to_obras(e2e.login())
    assert "Todavía no hay obras" in texts(at)

    at.text_input(key="nueva_nombre").input("Casa Lote 12")
    at.text_input(key="nueva_cliente").input("Pérez")
    at.selectbox(key="nueva_municipio").set_value("La Plata")
    at.selectbox(key="nueva_estado").set_value("En curso")
    at.number_input(key="nueva_presupuesto").set_value(85000.0)
    at.selectbox(key="nueva_moneda").set_value("USD")
    at = click(at, "Crear obra")

    assert not at.exception
    assert "Obra «Casa Lote 12» creada." in texts(at)
    guardada = obras.find_obras(e2e.db, "Lote 12")[0]
    assert guardada["municipio"] == "La Plata" and guardada["moneda"] == "USD"
    assert guardada["presupuesto"] == 85000.0 and guardada["estado"] == "En curso"

    at = at.run()  # siguiente carga: ya figura en el listado y en las métricas
    assert at.dataframe[0].value["nombre"].tolist() == ["Casa Lote 12"]
    assert [m.value for m in at.metric] == ["1", "1", "0%"]


def test_e2e_05_obra_sin_nombre(e2e):
    """E2E-05: no deja crear una obra sin nombre."""

    at = click(e2e.go_to_obras(e2e.login()), "Crear obra")

    assert "La obra necesita un nombre." in texts(at)
    assert obras.list_obras(e2e.db) == []


def test_e2e_06_actualizar_estado_y_avance(e2e):
    """E2E-06: cambia estado y avance de una obra y se refleja en el listado."""

    _seed(e2e.db)
    at = e2e.go_to_obras(e2e.login())
    at.selectbox(key="lista_obra").set_value(1).run()
    at.selectbox(key="upd_estado_1").set_value("Pausada")
    at.slider(key="upd_avance_1").set_value(55)
    at = click(at, "Guardar cambios")

    assert not at.exception
    obra = obras.get_obra(e2e.db, 1)
    assert (obra["estado"], obra["avance"]) == ("Pausada", 55)
    assert obras.get_obra(e2e.db, 2)["avance"] == 0  # la otra obra no se tocó


def test_e2e_07_filtrar_por_estado(e2e):
    """E2E-07: el filtro por estado deja solo las obras de ese estado."""

    _seed(e2e.db)
    at = e2e.go_to_obras(e2e.login())
    assert len(at.dataframe[0].value) == 2

    at = at.multiselect(key="lista_filtro").set_value(["En curso"]).run()

    assert at.dataframe[0].value["nombre"].tolist() == ["Casa Lote 12"]


def test_e2e_08_bitacora_manual(e2e):
    """E2E-08: agrega una nota en la bitácora con autor y fecha, y la muestra."""

    _seed(e2e.db)
    at = e2e.go_to_obras(e2e.login())
    at.selectbox(key="bitacora_obra").set_value(1)
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
    at.sidebar.selectbox[0].set_value(1).run()
    at = at.chat_input[0].set_value("¿Qué retiro de frente necesito?").run()

    assert not at.exception
    assert e2e.store.filters == [{"source": "Codigo Edificacion de La Plata.pdf"}]
    prompt = e2e.llm.seen[0][0].content
    assert "Casa Lote 12" in prompt and "código de edificación de La Plata" in prompt
    assert "el retiro de frente es de 3 m" in texts(at)


def test_e2e_12_sin_obra_activa_busca_en_todo(e2e):
    """E2E-12: sin obra activa, la búsqueda de normativa no se filtra."""

    _seed(e2e.db)
    e2e.script(AIMessage(content="Depende del municipio."))
    at = e2e.login().chat_input[0].set_value("¿Altura máxima permitida?").run()

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
    at = e2e.login().chat_input[0].set_value("¿Qué obras tengo en curso?").run()

    assert not at.exception
    resultado_herramienta = e2e.llm.seen[1][-1].content
    assert "Casa Lote 12" in resultado_herramienta and "Hudson" not in resultado_herramienta
    assert "Tenés 1 obra en curso" in texts(at)


def test_e2e_14_cargar_avance_y_nota_por_chat(e2e):
    """E2E-14: pedido por chat -> nota + avance guardados, avisos visibles y
    los cambios se ven después en la sección Obras."""

    _seed(e2e.db)
    e2e.script(
        tool_call("agregar_nota_bitacora", {"nota": "Hormigonado de platea"}, "c1"),
        tool_call("actualizar_obra", {"avance": 40}, "c2"),
        AIMessage(content="Listo: anoté la nota y pasé el avance a 40%."),
    )
    at = e2e.login()
    at.sidebar.selectbox[0].set_value(1).run()
    at = at.chat_input[0].set_value("Anotá que se hormigonó la platea, avance 40%").run()

    assert not at.exception
    pantalla = texts(at)
    assert "📝 Nota agregada a la bitácora de «Casa Lote 12»" in pantalla
    assert "✏️ «Casa Lote 12» actualizada: avance → 40%" in pantalla
    assert obras.list_bitacora(e2e.db, 1)[0]["autor"] == EMAIL

    at = e2e.go_to_obras(at)
    assert at.dataframe[0].value.set_index("nombre").loc["Casa Lote 12", "avance"] == 40
    at = at.selectbox(key="bitacora_obra").set_value(1).run()
    assert "Hormigonado de platea" in texts(at)


def test_e2e_15_obra_ambigua_no_escribe(e2e):
    """E2E-15: si la obra pedida es ambigua, no escribe nada y pide aclarar."""

    _seed(e2e.db)
    obras.create_obra(e2e.db, {"nombre": "Casa Lote 14"})
    e2e.script(
        tool_call("agregar_nota_bitacora", {"nota": "Llegó el hierro", "obra": "Casa Lote"}),
        AIMessage(content="¿En cuál obra? Casa Lote 12 o Casa Lote 14."),
    )
    at = e2e.login().chat_input[0].set_value("Anotá en Casa Lote que llegó el hierro").run()

    assert not at.exception
    assert "varias obras" in e2e.llm.seen[1][-1].content
    assert all(obras.list_bitacora(e2e.db, i) == [] for i in (1, 3))
    assert "📝" not in texts(at)


def test_e2e_16_historial_se_guarda(e2e):
    """E2E-16: pregunta y respuesta quedan en la tabla de historial del usuario."""

    e2e.script(AIMessage(content="La altura máxima es de 9 m."))
    e2e.login().chat_input[0].set_value("¿Altura máxima?").run()

    filas = e2e.db.tables["mensajes"]
    assert [(f["rol"], f["contenido"]) for f in filas] == [
        ("user", "¿Altura máxima?"),
        ("assistant", "La altura máxima es de 9 m."),
    ]
    assert {f["user_id"] for f in filas} == {f"id-{EMAIL}"}
