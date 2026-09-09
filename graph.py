"""Obra assistant built on LangGraph.

Pipeline: ``classify`` -> ``retrieve`` -> ``agente_obra``.

- ``classify`` tags the last question as ``normativa``, ``diseno`` or ``general``.
- ``retrieve`` returns retrieval context. For now it is a fixed stub string;
  the real Chroma-backed retrieval will replace it later.
- ``agente_obra`` calls Gemini (through LangChain) with the context + history.

The graph is compiled with a ``MemorySaver`` checkpointer, so passing a
``thread_id`` in the config keeps the conversation history across invocations.
"""

import os
from operator import add
from typing import Annotated, Literal, Optional, TypedDict

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

# Load GEMINI_API_KEY (and any other variables) from the local .env file.
load_dotenv()

Category = Literal["normativa", "diseno", "general"]

# Keyword buckets used by the (temporary) rule-based classifier.
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


class ObraState(TypedDict):
    """Graph state.

    ``mensajes`` is a plain list of strings and uses an additive reducer so the
    checkpointer accumulates the conversation instead of overwriting it.
    """

    mensajes: Annotated[list[str], add]
    category: Category
    context: str


def _create_llm() -> ChatGoogleGenerativeAI:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Set it in a local .env file."
        )
    return ChatGoogleGenerativeAI(
        model="models/gemini-3.6-flash", google_api_key=api_key
    )


def classify(state: ObraState) -> ObraState:
    """Classify the last question as normativa / diseno / general."""

    question = state["mensajes"][-1].lower()
    if any(keyword in question for keyword in _NORMATIVA_KEYWORDS):
        category: Category = "normativa"
    elif any(keyword in question for keyword in _DISENO_KEYWORDS):
        category = "diseno"
    else:
        category = "general"
    return {"category": category}


def retrieve(state: ObraState) -> ObraState:
    """Return retrieval context.

    Stub implementation: a fixed test string. Will be replaced by a real
    Chroma similarity search.
    """

    category = state.get("category", "general")
    context = (
        "[CONTEXTO DE PRUEBA] Fragmento normativo de ejemplo "
        f"(categoría: {category}). La altura máxima permitida en una vivienda "
        "unifamiliar en zona residencial es de 9 metros, equivalente a planta "
        "baja más dos niveles."
    )
    return {"context": context}


def build_graph(llm: Optional[BaseChatModel] = None) -> StateGraph:
    """Build the classify -> retrieve -> agente_obra graph.

    Pass ``llm`` to inject a fake chat model in tests; when omitted, a real
    Gemini client is created lazily inside the node.
    """

    def agente_obra(state: ObraState) -> ObraState:
        model = llm or _create_llm()
        system = SystemMessage(
            content=(
                "Sos un asistente de obra. Respondé la última consulta usando "
                "el contexto recuperado.\n\n"
                f"Categoría: {state.get('category', 'general')}\n"
                f"Contexto:\n{state.get('context', '')}"
            )
        )
        history = [HumanMessage(content=text) for text in state["mensajes"]]
        response = model.invoke([system, *history])
        return {"mensajes": [response.content]}

    graph = StateGraph(ObraState)
    graph.add_node("classify", classify)
    graph.add_node("retrieve", retrieve)
    graph.add_node("agente_obra", agente_obra)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "agente_obra")
    graph.add_edge("agente_obra", END)
    return graph


if __name__ == "__main__":
    app = build_graph().compile(checkpointer=MemorySaver())

    config = {"configurable": {"thread_id": "demo"}}
    question = "¿Cuál es la altura máxima permitida en una vivienda?"
    result = app.invoke({"mensajes": [question]}, config)

    print(result["mensajes"][-1])
