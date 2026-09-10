"""The retrieval-augmented graph.

Pipeline: ``classify`` -> ``retrieve`` -> ``agente_obra``.

- ``classify``   tags the last question as ``normativa`` / ``diseno`` / ``general``.
- ``retrieve``   runs a similarity search against the Chroma store.
- ``agente_obra`` answers with the OpenAI chat model, given context + history.

Compiled with a ``MemorySaver`` checkpointer, so a ``thread_id`` in the config
keeps the conversation across ``invoke`` calls.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.vectorstores import VectorStore
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from atrium.config import settings
from atrium.vectorstore import get_vector_store

Category = Literal["normativa", "diseno", "general"]

_NORMATIVA_KEYWORDS = (
    "altura",
    "permitid",
    "norma",
    "codigo",
    "código",
    "reglament",
    "retiro",
    "fot",
    "fos",
    "metros",
    "limite",
    "límite",
    "ordenanza",
    "habilitac",
    "zonificac",
)
_DISENO_KEYWORDS = (
    "diseno",
    "diseño",
    "fachada",
    "estetic",
    "estétic",
    "material",
    "color",
    "distribuc",
    "ambiente",
    "planta",
    "luz natural",
    "ventilac",
)

_SYSTEM_PROMPT = (
    "Sos un asistente de obra. Respondé la última consulta usando el contexto "
    "recuperado.\n\nCategoría: {category}\nContexto:\n{context}"
)
_NO_CONTEXT = "(no se encontraron fragmentos relevantes en la base de conocimiento)"


class ObraState(TypedDict):
    """Graph state.

    ``mensajes`` is a list of plain strings with an additive reducer, so the
    checkpointer accumulates the conversation instead of overwriting it.
    """

    mensajes: Annotated[list[str], add]
    category: Category
    context: str


def classify(state: ObraState) -> ObraState:
    """Rule-based classifier over the last question (no LLM call)."""

    question = state["mensajes"][-1].lower()
    if any(word in question for word in _NORMATIVA_KEYWORDS):
        category: Category = "normativa"
    elif any(word in question for word in _DISENO_KEYWORDS):
        category = "diseno"
    else:
        category = "general"
    return {"category": category}


def format_context(docs: list[Document]) -> str:
    """Render retrieved chunks as a single prompt-ready block."""

    if not docs:
        return _NO_CONTEXT
    return "\n\n---\n\n".join(
        f"[{doc.metadata.get('source', '?')} — pág. {doc.metadata.get('page', '?')}]\n"
        f"{doc.page_content}"
        for doc in docs
    )


def _create_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )


def build_graph(
    llm: BaseChatModel | None = None,
    vector_store: VectorStore | None = None,
) -> StateGraph:
    """Assemble the graph.

    Pass ``llm`` / ``vector_store`` to inject fakes in tests; otherwise the real
    OpenAI client and on-disk Chroma store are created lazily inside the nodes.
    """

    def retrieve(state: ObraState) -> ObraState:
        store = vector_store or get_vector_store()
        docs = store.similarity_search(state["mensajes"][-1], k=settings.retrieval_k)
        return {"context": format_context(docs)}

    def agente_obra(state: ObraState) -> ObraState:
        model = llm or _create_llm()
        system = SystemMessage(
            content=_SYSTEM_PROMPT.format(
                category=state.get("category", "general"),
                context=state.get("context", ""),
            )
        )
        history = [HumanMessage(content=text) for text in state["mensajes"]]
        response = model.invoke([system, *history])
        # .text flattens both plain-string and structured (list) content.
        return {"mensajes": [response.text]}

    graph = StateGraph(ObraState)
    graph.add_node("classify", classify)
    graph.add_node("retrieve", retrieve)
    graph.add_node("agente_obra", agente_obra)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "agente_obra")
    graph.add_edge("agente_obra", END)
    return graph
