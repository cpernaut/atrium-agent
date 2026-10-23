"""The agent connected to the obras tracker: active obra and tool calls."""

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from atrium import obras, propuestas
from atrium.rag import build_graph
from tests.fake_supabase import FakeSupabase
from tests.fakes import RecordingStore, ToolCallingFake, tool_call

_call = tool_call


def _app(db, replies, store=None):
    llm = ToolCallingFake(messages=iter(replies), seen=[])
    graph = build_graph(llm=llm, vector_store=store or RecordingStore(), obras_client=db)
    return graph.compile(checkpointer=MemorySaver()), llm


def _db():
    db = FakeSupabase()
    obras.create_obra(
        db, {"nombre": "Casa Lote 12", "municipio": "La Plata", "estado": "En curso", "avance": 30}
    )
    obras.create_obra(db, {"nombre": "Ampliación Hudson", "municipio": "Berazategui"})
    return db


def test_active_obra_limits_normativa_and_reaches_prompt():
    db, store = _db(), RecordingStore()
    app, llm = _app(db, [AIMessage(content="Necesitás 3 m de retiro.")], store)

    result = app.invoke(
        {"mensajes": ["¿Qué retiro de frente necesito?"], "obra_id": 1},
        {"configurable": {"thread_id": "t1"}},
    )

    assert store.filters == [{"source": "Codigo Edificacion de La Plata.pdf"}]
    system_prompt = llm.seen[0][0].content
    assert "Casa Lote 12" in system_prompt and "La Plata" in system_prompt
    assert result["propuestas"] == []


def test_without_active_obra_search_is_unfiltered():
    store = RecordingStore()
    app, _ = _app(_db(), [AIMessage(content="ok")], store)
    app.invoke(
        {"mensajes": ["altura máxima"], "obra_id": None}, {"configurable": {"thread_id": "t2"}}
    )
    assert store.filters == [None]


def test_agent_reads_obras_through_tool():
    app, llm = _app(
        _db(),
        [
            _call("listar_obras", {"estado": "En curso"}),
            AIMessage(content="Tenés 1 obra en curso: Casa Lote 12."),
        ],
    )

    result = app.invoke(
        {"mensajes": ["¿Qué obras tengo en curso?"], "obra_id": None},
        {"configurable": {"thread_id": "t3"}},
    )

    tool_result = [m for m in llm.seen[1] if isinstance(m, ToolMessage)][0].content
    assert "Casa Lote 12" in tool_result and "Hudson" not in tool_result
    assert result["mensajes"][-1] == "Tenés 1 obra en curso: Casa Lote 12."


def test_agent_proposes_note_and_progress_and_saves_only_when_confirmed():
    db = _db()
    app, _ = _app(
        db,
        [
            _call("agregar_nota_bitacora", {"nota": "Hormigonado de platea"}, "c1"),
            _call("actualizar_obra", {"avance": 40}, "c2"),
            AIMessage(content="Listo: anoté la nota y pasé el avance a 40%."),
        ],
    )

    result = app.invoke(
        {"mensajes": ["Anotá que hoy se hormigonó la platea y pasá el avance a 40%"], "obra_id": 1},
        {"configurable": {"thread_id": "t4"}},
    )

    assert [p["tipo"] for p in result["propuestas"]] == [propuestas.NOTA, propuestas.OBRA]
    assert obras.list_bitacora(db, 1) == [] and obras.get_obra(db, 1)["avance"] == 30

    hechos = [propuestas.ejecutar(db, "caro@x.com", p) for p in result["propuestas"]]
    nota = obras.list_bitacora(db, 1)[0]
    assert nota["nota"] == "Hormigonado de platea" and nota["autor"] == "caro@x.com"
    assert obras.get_obra(db, 1)["avance"] == 40
    assert hechos[1] == "✏️ «Casa Lote 12» actualizada: avance → 40%"


def test_ambiguous_obra_is_not_written():
    db = _db()
    obras.create_obra(db, {"nombre": "Casa Lote 14"})
    app, llm = _app(
        db,
        [
            _call("agregar_nota_bitacora", {"nota": "x", "obra": "Casa Lote"}),
            AIMessage(content="¿En cuál de las dos obras?"),
        ],
    )

    result = app.invoke(
        {"mensajes": ["Anotá x en Casa Lote"], "obra_id": None},
        {"configurable": {"thread_id": "t5"}},
    )

    assert "varias obras" in [m for m in llm.seen[1] if isinstance(m, ToolMessage)][0].content
    assert obras.list_bitacora(db, 1) == [] and result["propuestas"] == []


def test_tool_errors_reach_the_model_instead_of_crashing():
    db = _db()
    app, llm = _app(
        db,
        [
            _call("actualizar_obra", {"obra": "1", "avance": 150}),
            AIMessage(content="El avance tiene que ser entre 0 y 100."),
        ],
    )
    app.invoke(
        {"mensajes": ["poné 150% en lote 12"], "obra_id": None},
        {"configurable": {"thread_id": "t6"}},
    )
    assert "entre 0 y 100" in [m for m in llm.seen[1] if isinstance(m, ToolMessage)][0].content
    assert obras.get_obra(db, 1)["avance"] == 30
