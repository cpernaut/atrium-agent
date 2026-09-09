"""Graph tests that use a fake chat model instead of a real LLM API.

``GenericFakeChatModel`` lives in ``langchain_core.language_models.fake_chat_models``
(and is re-exported from ``langchain_core.language_models``).
"""

import itertools

from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langgraph.checkpoint.memory import MemorySaver

from graph import build_graph

FAKE_REPLY = "Respuesta de prueba del agente de obra."


class _FakeVectorStore:
    """Stand-in for Chroma so tests never hit the embeddings API."""

    def similarity_search(self, query, k=4):
        return [
            Document(
                page_content="La altura máxima permitida es de 9 metros.",
                metadata={"source": "fake.pdf", "page": 1},
            )
        ]


def _build_app():
    # cycle -> the fake model never runs out of canned replies.
    fake_llm = GenericFakeChatModel(messages=itertools.cycle([FAKE_REPLY]))
    graph = build_graph(llm=fake_llm, vector_store=_FakeVectorStore())
    return graph.compile(checkpointer=MemorySaver())


def test_graph_returns_non_empty_answer():
    app = _build_app()
    config = {"configurable": {"thread_id": "t-answer"}}

    result = app.invoke(
        {"mensajes": ["¿Cuál es la altura máxima permitida en una vivienda?"]},
        config,
    )

    answer = result["mensajes"][-1]
    assert isinstance(answer, str)
    assert answer.strip() != ""


def test_thread_id_keeps_history_between_invocations():
    app = _build_app()
    config = {"configurable": {"thread_id": "t-history"}}

    app.invoke({"mensajes": ["Primera pregunta"]}, config)
    result = app.invoke({"mensajes": ["Segunda pregunta"]}, config)

    mensajes = result["mensajes"]
    # 2 questions + 2 answers accumulated on the same thread.
    assert len(mensajes) == 4
    assert mensajes[0] == "Primera pregunta"
    assert mensajes[2] == "Segunda pregunta"

    # The checkpointer holds the same accumulated history.
    stored = app.get_state(config).values["mensajes"]
    assert stored == mensajes

    # A different thread_id starts from an empty history.
    other = app.invoke({"mensajes": ["Otra pregunta"]}, {"configurable": {"thread_id": "t-fresh"}})
    assert len(other["mensajes"]) == 2
