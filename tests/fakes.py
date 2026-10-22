"""Test doubles shared by the agent tests and the E2E suite."""

from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class RecordingStore:
    """Vector store that returns one fixed chunk and records the filters used."""

    def __init__(self, text="Retiro de frente: 3 m."):
        self.text = text
        self.filters = []

    def similarity_search(self, query, k=4, filter=None):  # noqa: A002 - Chroma's name
        self.filters.append(filter)
        return [Document(page_content=self.text, metadata={"source": "x.pdf", "page": 1})]


class ToolCallingFake(GenericFakeChatModel):
    """Replays scripted AIMessages and records what it was sent."""

    seen: list = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        self.seen.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


def tool_call(name, args, call_id="c1"):
    """An AIMessage asking to run one tool."""

    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])
