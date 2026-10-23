"""The retrieval-augmented graph.

Pipeline: ``classify`` -> ``retrieve`` -> ``agente_obra``.

- ``classify``   tags the last question as ``normativa`` / ``diseno`` / ``general``.
- ``retrieve``   runs a similarity search against the Chroma store. When an obra
                 is active, the search is limited to its municipio's building code.
- ``agente_obra`` answers with the OpenAI chat model, given context + history.
                 With an ``obras_client`` it can also call tools to read and
                 update the obras tracker (see ``atrium.obra_tools``).

Compiled with a ``MemorySaver`` checkpointer, so a ``thread_id`` in the config
keeps the conversation across ``invoke`` calls.
"""

from __future__ import annotations

from operator import add
from typing import TYPE_CHECKING, Annotated, Literal, TypedDict

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.vectorstores import VectorStore
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from atrium import obras
from atrium.config import settings
from atrium.obra_tools import build_obra_tools
from atrium.vectorstore import get_vector_store

if TYPE_CHECKING:
    from supabase import Client

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
    "recuperado.\n\n{obra}\n\nCategoría: {category}\nContexto:\n{context}"
)
_TOOLS_PROMPT = (
    "\n\nTenés herramientas para consultar y actualizar el tracker de obras del "
    "equipo. Usalas para responder sobre las obras con datos reales, nunca los "
    "inventes. Solo agregá notas o cambiás avance/estado cuando el usuario lo pide "
    "explícitamente; si la obra es ambigua, preguntá antes de escribir. También "
    "tenés la lista de proveedores del equipo: nunca des de alta un proveedor sin "
    "que el usuario lo pida o lo confirme, y nunca califiques proveedores. Después "
    "de escribir, confirmá en una línea qué guardaste."
)
_NO_CONTEXT = "(no se encontraron fragmentos relevantes en la base de conocimiento)"
_MAX_TOOL_ROUNDS = 5


class ObraState(TypedDict):
    """Graph state.

    ``mensajes`` is a list of plain strings with an additive reducer, so the
    checkpointer accumulates the conversation instead of overwriting it.
    """

    mensajes: Annotated[list[str], add]
    category: Category
    context: str
    obra_id: int | None  # obra picked in the UI; set on every invoke
    obra: str  # prompt-ready description of the active obra
    acciones: list[str]  # writes done by tools in this turn, for the UI


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


def _obra_block(obra: obras.Obra | None) -> str:
    if obra is None:
        return "No hay una obra activa seleccionada."
    texto = "Obra activa:\n" + obras.describe_obra(obra)
    if obras.normativa_source(obra):
        texto += f"\nEl contexto recuperado es del código de edificación de {obra['municipio']}."
    elif obra.get("municipio"):
        texto += (
            f"\nNo hay normativa cargada para {obra['municipio']}: aclaralo si la "
            "pregunta es de normativa."
        )
    return texto


def build_graph(
    llm: BaseChatModel | None = None,
    vector_store: VectorStore | None = None,
    obras_client: Client | None = None,
    autor: str | None = None,
) -> StateGraph:
    """Assemble the graph.

    Pass ``llm`` / ``vector_store`` to inject fakes in tests; otherwise the real
    OpenAI client and on-disk Chroma store are created lazily inside the nodes.
    Pass the signed-in user's Supabase client as ``obras_client`` to connect the
    obras tracker (active obra + tools); ``autor`` signs bitácora notes.
    """

    def _active_obra(state: ObraState) -> obras.Obra | None:
        obra_id = state.get("obra_id")
        if obras_client is None or obra_id is None:
            return None
        try:
            return obras.get_obra(obras_client, obra_id)
        except obras.ObrasError:
            return None

    def retrieve(state: ObraState) -> ObraState:
        store = vector_store or get_vector_store()
        obra = _active_obra(state)
        source = obras.normativa_source(obra)
        kwargs = {"filter": {"source": source}} if source else {}
        docs = store.similarity_search(state["mensajes"][-1], k=settings.retrieval_k, **kwargs)
        return {"context": format_context(docs), "obra": _obra_block(obra)}

    def agente_obra(state: ObraState) -> ObraState:
        model = llm or _create_llm()
        prompt = _SYSTEM_PROMPT.format(
            obra=state.get("obra") or _obra_block(None),
            category=state.get("category", "general"),
            context=state.get("context", ""),
        )
        acciones: list[str] = []
        tools = []
        if obras_client is not None:
            tools = build_obra_tools(obras_client, autor, lambda: state.get("obra_id"), acciones)
            prompt += _TOOLS_PROMPT

        messages: list[BaseMessage] = [
            SystemMessage(content=prompt),
            *(HumanMessage(content=text) for text in state["mensajes"]),
        ]
        response = _run_with_tools(model, tools, messages)
        # .text flattens both plain-string and structured (list) content.
        return {"mensajes": [response.text], "acciones": acciones}

    graph = StateGraph(ObraState)
    graph.add_node("classify", classify)
    graph.add_node("retrieve", retrieve)
    graph.add_node("agente_obra", agente_obra)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "agente_obra")
    graph.add_edge("agente_obra", END)
    return graph


def _run_with_tools(model: BaseChatModel, tools: list, messages: list[BaseMessage]):
    """Call the model, executing any tool calls, until it gives a final answer."""

    if not tools:
        return model.invoke(messages)

    bound = model.bind_tools(tools)
    by_name = {tool.name: tool for tool in tools}
    for _ in range(_MAX_TOOL_ROUNDS):
        response = bound.invoke(messages)
        if not response.tool_calls:
            return response
        messages.append(response)
        for call in response.tool_calls:
            tool = by_name.get(call["name"])
            try:
                output = (
                    tool.invoke(call["args"])
                    if tool
                    else f"No existe la herramienta {call['name']}."
                )
            except Exception as exc:  # noqa: BLE001 - report bad args back to the model
                output = f"Error al ejecutar {call['name']}: {exc}"
            messages.append(ToolMessage(content=str(output), tool_call_id=call["id"]))
    # Too many rounds: ask for an answer with what it has, without more tools.
    return model.invoke(messages)
