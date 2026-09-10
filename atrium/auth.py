"""Supabase authentication. No Streamlit dependency."""

from __future__ import annotations

import contextlib
from typing import Any

from supabase import Client, create_client

from atrium.config import settings


def create_supabase() -> Client:
    """A fresh Supabase client (holds its own auth session once signed in)."""

    return create_client(settings.supabase_url, settings.supabase_anon_key)


def sign_in(client: Client, email: str, password: str) -> Any:
    """Sign in with email + password. Returns the Supabase user.

    Raises ``supabase.AuthApiError`` on bad credentials.
    """

    result = client.auth.sign_in_with_password({"email": email, "password": password})
    return result.user


def sign_out(client: Client) -> None:
    # The local session is cleared by the caller regardless of the API result.
    with contextlib.suppress(Exception):
        client.auth.sign_out()
