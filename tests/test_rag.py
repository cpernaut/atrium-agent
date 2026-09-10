"""Graph behaviour, exercised with a fake chat model and a fake vector store
so nothing hits a real API."""

import itertools

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langgraph.checkpoint.memory import MemorySaver

from atrium.rag import build_graph

FAKE_REPLY = "Respuesta de prueba del agente de obra."


class FakeVectorStore:
    def similarity_search(self, query, k=4):
        return [
            Document(
                page_content="La altura máxima permitida es de 9 metros.",
                metadata={"source": "fake.pdf", "page": 1},
            )
        ]


@pytest.fixture
def app():
    llm = GenericFakeChatModel(messages=itertools.cycle([FAKE_REPLY]))
    graph = build_graph(llm=llm, vector_store=FakeVectorStore())
    return graph.compile(checkpointer=MemorySaver())


def test_returns_non_empty_answer(app):
    result = app.invoke(
        {"mensajes": ["¿Cuál es la altura máxima permitida en una vivienda?"]},
        {"configurable": {"thread_id": "t-answer"}},
    )
    answer = result["mensajes"][-1]
    assert isinstance(answer, str) and answer.strip()


def test_retrieved_context_reaches_state(app):
    result = app.invoke(
        {"mensajes": ["altura máxima"]},
        {"configurable": {"thread_id": "t-context"}},
    )
    assert "9 metros" in result["context"]


def test_thread_id_keeps_history_between_invocations(app):
    config = {"configurable": {"thread_id": "t-history"}}
    app.invoke({"mensajes": ["Primera pregunta"]}, config)
    result = app.invoke({"mensajes": ["Segunda pregunta"]}, config)

    mensajes = result["mensajes"]
    assert len(mensajes) == 4  # 2 questions + 2 answers
    assert mensajes[0] == "Primera pregunta"
    assert mensajes[2] == "Segunda pregunta"
    assert app.get_state(config).values["mensajes"] == mensajes


def test_other_thread_starts_fresh(app):
    app.invoke({"mensajes": ["hola"]}, {"configurable": {"thread_id": "t-a"}})
    other = app.invoke({"mensajes": ["hola"]}, {"configurable": {"thread_id": "t-b"}})
    assert len(other["mensajes"]) == 2
