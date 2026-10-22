"""Harness for the end-to-end suite.

Runs the real ``app.py`` with Streamlit's ``AppTest`` (the same script the
deployed app runs: login, sidebar, Obras pages, agent graph and tools), and
swaps only the external services:

- Supabase -> ``E2ESupabase`` (in-memory tables + a fake auth with one user)
- OpenAI chat model -> a scripted ``ToolCallingFake``
- Chroma -> ``RecordingStore``
- Dólar MEP source -> ``Harness.mep`` (a dict of quotes by date)

Nothing touches the network, so the suite is fast, free and deterministic.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest
from supabase import AuthApiError

import atrium.auth
import atrium.rag
import atrium.vectorstore
from atrium import cotizaciones, finanzas
from tests.fake_supabase import FakeSupabase, seed_rubros
from tests.fakes import RecordingStore, ToolCallingFake

APP = str(Path(__file__).resolve().parents[2] / "app.py")
EMAIL, PASSWORD = "caro@atrium.test", "secreto-123"


class FakeAuth:
    def __init__(self, users: dict[str, str]):
        self.users = users
        self.signed_out = 0

    def sign_in_with_password(self, credentials):
        email, password = credentials["email"], credentials["password"]
        if self.users.get(email) != password:
            raise AuthApiError("Invalid login credentials", 400, "invalid_credentials")
        return SimpleNamespace(user=SimpleNamespace(id=f"id-{email}", email=email))

    def sign_out(self):
        self.signed_out += 1


class E2ESupabase(FakeSupabase):
    def __init__(self):
        super().__init__()
        self.auth = FakeAuth({EMAIL: PASSWORD})
        seed_rubros(self)  # like the precarga in supabase_schema.sql


class Harness:
    """One fake world (db + model + store) shared by every page load of a test."""

    def __init__(self):
        self.db = E2ESupabase()
        self.store = RecordingStore()
        self.llm = ToolCallingFake(messages=iter([]), seen=[])
        # MEP quotes served by the fake source: {date: (compra, venta)}.
        # By default the last 30 days quote 1190/1210 (average 1200).
        hoy = finanzas.hoy()
        self.mep = {hoy - timedelta(days=d): (1190, 1210) for d in range(30)}
        self.mep_caido = False

    def fetch_mep(self):
        if self.mep_caido:
            raise cotizaciones.CotizacionError("timeout")
        return [
            {"casa": "bolsa", "fecha": f.isoformat(), "compra": c, "venta": v}
            for f, (c, v) in self.mep.items()
        ]

    def set_mep(self, quotes: dict[date, tuple[float, float]]):
        self.mep = dict(quotes)
        cotizaciones.clear_cache()

    def script(self, *replies):
        """Next answers of the chat model, in order (AIMessages or tool calls)."""

        self.llm = ToolCallingFake(messages=iter(replies), seen=[])

    # page helpers ---------------------------------------------------------
    def open(self) -> AppTest:
        return AppTest.from_file(APP, default_timeout=30).run()

    def login(self, email=EMAIL, password=PASSWORD) -> AppTest:
        at = self.open()
        at.text_input(key="login_email").input(email)
        at.text_input(key="login_password").input(password)
        return click(at, "Ingresar")

    def go_to_obras(self, at: AppTest) -> AppTest:
        """The app opens on Obras (#33): there is no section to pick, only a reload."""

        return at.run()

    def abrir_agente(self, at: AppTest) -> AppTest:
        """Open the floating agent (bottom right) if it is closed."""

        if any(b.key == "agente_abrir" for b in at.button):
            at = at.button(key="agente_abrir").click().run()
        return at

    def elegir_obra(self, at: AppTest, obra_id: int) -> AppTest:
        """The single obra picker at the top of the page (UX-02)."""

        return at.selectbox(key="obra_elegida").set_value(obra_id).run()


def click(at: AppTest, label: str) -> AppTest:
    """Click the (form submit) button with this label and rerun."""

    matches = [b for b in at.button if b.label == label]
    assert matches, f"no button «{label}»; buttons: {[b.label for b in at.button]}"
    return matches[0].click().run()


def texts(at: AppTest) -> str:
    """Everything visible as text, to assert on what the user would read."""

    parts = []
    for kind in ("markdown", "caption", "error", "success", "info", "warning", "title"):
        parts += [str(el.value) for el in getattr(at, kind)]
    # Markdown escapes (from texto_seguro) removed: this is what the user reads.
    # Security tests inspect the raw element values instead.
    return re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", "\n".join(parts))


@pytest.fixture
def e2e(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-e2e")
    monkeypatch.setenv("SUPABASE_URL", "https://e2e.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-e2e")
    harness = Harness()
    monkeypatch.setattr(atrium.auth, "create_supabase", lambda: harness.db)
    monkeypatch.setattr(atrium.rag, "_create_llm", lambda: harness.llm)
    monkeypatch.setattr(atrium.rag, "get_vector_store", lambda: harness.store)
    monkeypatch.setattr(atrium.vectorstore, "collection_size", lambda: 42)
    monkeypatch.setattr(cotizaciones, "_fetch_json", harness.fetch_mep)
    cotizaciones.clear_cache()
    yield harness
    cotizaciones.clear_cache()


# --------------------------------------------------------------------------- #
# Budget table (#45): rows are horizontal blocks of columns
# --------------------------------------------------------------------------- #
def _hijos(nodo):
    hijos = getattr(nodo, "children", None)
    return list(hijos.values()) if isinstance(hijos, dict) else list(hijos or [])


def _textos(nodo) -> list[str]:
    """Visible text inside a node: markdown values and button labels."""

    propio = []
    if getattr(nodo, "type", None) == "markdown" or nodo.__class__.__name__ == "Markdown":
        propio.append(str(nodo.value))
    elif nodo.__class__.__name__ == "Button":
        propio.append(str(nodo.label))
    return propio + [t for h in _hijos(nodo) for t in _textos(h)]


def _claves(nodo) -> set[str]:
    propias = {nodo.key} if getattr(nodo, "key", None) else set()
    return propias.union(*(_claves(h) for h in _hijos(nodo)))


def fila_tabla(at: AppTest, key: str) -> list[str]:
    """Cells of the budget-table row that holds the widget ``key`` (as the user reads them).

    Each cell is the text of one column; markdown escapes are removed.
    """

    def buscar(nodo):
        hijos = _hijos(nodo)
        columnas = [h for h in hijos if h.__class__.__name__ == "Column"]
        if len(columnas) == 8 and key in _claves(nodo):
            return nodo
        for h in hijos:
            encontrado = buscar(h)
            if encontrado is not None:
                return encontrado
        return None

    fila = buscar(at._tree)
    assert fila is not None, f"no hay una fila de la tabla con «{key}»"
    celdas = [" ".join(_textos(c)) for c in _hijos(fila) if c.__class__.__name__ == "Column"]
    return [re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", c).strip() for c in celdas]


def abrir_presupuesto(at: AppTest, db) -> AppTest:
    """Expand every rubro and ítem of the budget table (as if the user opened them)."""

    claves = {f"r{i['rubro_id']}" for i in db.tables.get("presupuesto_items", [])}
    claves |= {f"i{i['id']}" for i in db.tables.get("presupuesto_items", [])}
    at.session_state["presupuesto_abiertos"] = claves
    return at.run()


def _sin_gris(celda: str) -> str:
    """First amount of a cell («ARS 1.200.000 :gray[USD 1.000]» -> «ARS 1.200.000»)."""

    return re.sub(r"\s*:gray\[.*?\]", "", celda).strip()


def tabla_rubros(at: AppTest) -> dict[str, dict[str, str]]:
    """Rubro rows of the budget table: {rubro: {column: text}}; Estado without its icon."""

    from plata_ui import COLUMNAS

    filas = {}
    for b in at.button:
        if b.key and b.key.startswith("fila_rubro_"):
            celdas = fila_tabla(at, b.key)
            nombre = re.sub(r"^[▸▾]\s*", "", celdas[0]).strip("* ")
            datos = dict(zip(COLUMNAS, celdas, strict=True))
            datos["Estado"] = re.sub(r"^\W+\s*", "", datos["Estado"]).split(" · ")[0]
            filas[nombre] = datos
    return filas


def tabla_items(at: AppTest) -> list[dict[str, str]]:
    """Ítem rows of the budget table, in order (only the ones visible)."""

    from plata_ui import COLUMNAS

    filas = []
    for b in at.button:
        if b.key and b.key.startswith("fila_item_"):
            celdas = fila_tabla(at, b.key)
            datos = dict(zip(COLUMNAS, celdas, strict=True))
            datos["nombre"] = re.sub(r"^[▸▾]\s*", "", celdas[0])
            datos["id"] = int(b.key.rsplit("_", 1)[1])
            filas.append(datos)
    return filas
