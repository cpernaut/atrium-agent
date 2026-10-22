"""Fixtures for the live suite: runs against the REAL Supabase project.

Skipped unless these env vars are set (GitHub Actions secrets in the
"E2E contra Supabase" workflow):

    E2E_SUPABASE_URL, E2E_SUPABASE_ANON_KEY, E2E_SUPABASE_SERVICE_ROLE_KEY

The service key is used only to create two throwaway users and to clean up
afterwards; every check runs with the anon key, as the app does. Everything
the suite creates is named ``[E2E] …`` and deleted at the end, even on failure.
"""

from __future__ import annotations

import os
import secrets
import uuid
from types import SimpleNamespace

import pytest
from supabase import Client, create_client

REQUIRED = ("E2E_SUPABASE_URL", "E2E_SUPABASE_ANON_KEY", "E2E_SUPABASE_SERVICE_ROLE_KEY")
PREFIX = "[E2E]"


def pytest_collection_modifyitems(config, items):
    missing = [name for name in REQUIRED if not os.getenv(name)]
    if not missing:
        return
    skip = pytest.mark.skip(reason=f"suite contra Supabase real: faltan {', '.join(missing)}")
    for item in items:
        if "tests/live" in str(item.fspath):
            item.add_marker(skip)


def _env(name: str) -> str:
    return os.environ[name]


def anon_client() -> Client:
    return create_client(_env("E2E_SUPABASE_URL"), _env("E2E_SUPABASE_ANON_KEY"))


@pytest.fixture(scope="session")
def admin() -> Client:
    return create_client(_env("E2E_SUPABASE_URL"), _env("E2E_SUPABASE_SERVICE_ROLE_KEY"))


@pytest.fixture(scope="session")
def run_id() -> str:
    return uuid.uuid4().hex[:8]


def _make_user(admin: Client, run_id: str, label: str):
    email = f"e2e-{label}-{run_id}@atrium.test"
    password = secrets.token_urlsafe(18)
    created = admin.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    ).user
    client = anon_client()
    client.auth.sign_in_with_password({"email": email, "password": password})
    return SimpleNamespace(id=created.id, email=email, client=client)


@pytest.fixture(scope="session")
def users(admin, run_id):
    """Two signed-in team members, A and B. Removed with all their data at the end."""

    made = []
    try:
        made.append(_make_user(admin, run_id, "a"))
        made.append(_make_user(admin, run_id, "b"))
        yield SimpleNamespace(a=made[0], b=made[1])
    finally:
        cleanup(admin, [u.id for u in made])


def cleanup(admin: Client, user_ids: list[str]) -> None:
    # Obras first (bitácora goes with them via ON DELETE CASCADE), then any
    # leftover rows that point at the users, then the users themselves.
    # (gastos and presupuesto_items also go with their obra via ON DELETE CASCADE).
    admin.table("obras").delete().like("nombre", f"{PREFIX}%").execute()
    for user_id in user_ids:
        for tabla in ("gastos", "presupuesto_items", "bitacora"):
            admin.table(tabla).delete().eq("creado_por", user_id).execute()
        admin.table("obras").delete().eq("creado_por", user_id).execute()
        admin.table("rubros").delete().eq("creado_por", user_id).execute()
        admin.table("mensajes").delete().eq("user_id", user_id).execute()
        admin.auth.admin.delete_user(user_id)


@pytest.fixture
def obra_de_a(users, run_id):
    """A fresh obra created by user A through RLS."""

    nombre = f"{PREFIX} Casa {run_id}-{uuid.uuid4().hex[:4]}"
    fila = (
        users.a.client.table("obras")
        .insert({"nombre": nombre, "municipio": "La Plata"})
        .execute()
        .data[0]
    )
    return fila
