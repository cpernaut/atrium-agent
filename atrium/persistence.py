"""Chat-history persistence in Supabase (table ``mensajes``).

See ``supabase_schema.sql`` for the table + RLS. No Streamlit dependency; the
caller decides how to surface a ``PersistenceError`` (the UI treats it as
non-fatal).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from supabase import Client

TABLE = "mensajes"

Role = Literal["user", "assistant"]


class PersistenceError(RuntimeError):
    """Reading or writing chat history failed."""


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


def load_history(client: Client, user_id: str) -> list[ChatMessage]:
    """Every stored message for ``user_id``, oldest first."""

    try:
        rows = (
            client.table(TABLE)
            .select("rol, contenido, created_at")
            .eq("user_id", user_id)
            .order("created_at")
            .execute()
            .data
        )
    except Exception as exc:  # noqa: BLE001 - wrap the provider error
        raise PersistenceError(str(exc)) from exc
    return [ChatMessage(role=row["rol"], content=row["contenido"]) for row in rows]


def save_exchange(
    client: Client,
    user_id: str,
    thread_id: str,
    question: str,
    answer: str,
) -> None:
    """Persist the user question and the agent answer as two rows."""

    now = datetime.now(UTC).isoformat()
    rows = [
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "rol": role,
            "contenido": text,
            "created_at": now,
        }
        for role, text in (("user", question), ("assistant", answer))
    ]
    try:
        client.table(TABLE).insert(rows).execute()
    except Exception as exc:  # noqa: BLE001 - wrap the provider error
        raise PersistenceError(str(exc)) from exc
