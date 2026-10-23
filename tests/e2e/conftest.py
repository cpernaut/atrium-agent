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
from streamlit.util import calc_hash
from supabase import AuthApiError

import atrium.auth
import atrium.rag
import atrium.vectorstore
import navegacion
from atrium import cotizaciones, finanzas
from tests.fake_supabase import FakeSupabase, seed_rubros
from tests.fakes import RecordingStore, ToolCallingFake

APP = str(Path(__file__).resolve().parents[2] / "app.py")
EMAIL, PASSWORD = "caro@atrium.test", "secreto-123"


class FakeAuth:
    """Supabase Auth with fixed users; keeps each user's metadata between logins."""

    def __init__(self, users: dict[str, str]):
        self.users = users
        self.signed_out = 0
        self.metadata: dict[str, dict] = {email: {} for email in users}
        self.actual: str | None = None
        self.updates: list[dict] = []
        self.falla_update = False

    def sign_in_with_password(self, credentials):
        email, password = credentials["email"], credentials["password"]
        if self.users.get(email) != password:
            raise AuthApiError("Invalid login credentials", 400, "invalid_credentials")
        self.actual = email
        user = SimpleNamespace(
            id=f"id-{email}", email=email, user_metadata=dict(self.metadata[email])
        )
        return SimpleNamespace(user=user)

    def update_user(self, atributos):
        if self.falla_update:
            raise AuthApiError("network down", 500, "unexpected_failure")
        self.updates.append(atributos)
        self.metadata[self.actual].update(atributos.get("data", {}))
        return SimpleNamespace(user=None)

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
        """🏗️ Obra activa: the screen the app opens on (#49)."""

        return ir_a(at, "obra")

    def ir_a(self, at: AppTest, url: str) -> AppTest:
        return ir_a(at, url)

    def abrir_agente(self, at: AppTest) -> AppTest:
        """Open the floating agent (bottom right) if it is closed."""

        if any(b.key == "agente_abrir" for b in at.button):
            at = at.button(key="agente_abrir").click().run()
        return at

    def elegir_obra(self, at: AppTest, obra_id: int) -> AppTest:
        """The obra activa picker in the left menu (UX-02, #49)."""

        return at.selectbox(key="obra_elegida").set_value(obra_id).run()


def ir_a(at: AppTest, url: str) -> AppTest:
    """Open a screen of the left menu (#49) by its url_path, as a click on it would.

    AppTest has no menu to click, so this selects the page the way Streamlit
    identifies it: by the hash of its url_path.
    """

    at._page_hash = calc_hash(url)
    return at.run()


def _run_siguiendo_la_pagina(run_original):
    """AppTest.run that stays on the screen the app switched to.

    In the browser ``st.switch_page`` changes the URL, so the next rerun is on
    the new screen; AppTest would go back to the previous one. After each run
    this points AppTest at the screen the app reports as current.
    """

    def run(self, *args, **kwargs):
        resultado = run_original(self, *args, **kwargs)
        try:
            actual = self.session_state[navegacion.ACTUAL]
        except KeyError:
            actual = None
        if actual:
            self._page_hash = calc_hash(actual)
        return resultado

    return run


def pagina_actual(at: AppTest) -> str:
    """Header of the screen on display (or the first tab, on 🏗️ Obra activa)."""

    if at.header:
        return at.header[0].value
    return at.tabs[0].label if at.tabs else ""


def click(at: AppTest, label: str) -> AppTest:
    """Click the (form submit) button with this label and rerun."""

    matches = [b for b in at.button if b.label == label]
    assert matches, f"no button «{label}»; buttons: {[b.label for b in at.button]}"
    return matches[0].click().run()


def botones_propuesta(at: AppTest, accion: str = "confirmar") -> list:
    """The «Confirmar» (or «Cancelar») buttons of the agent's pending propuestas."""

    return [b for b in at.button if str(b.key or "").startswith(f"propuesta_{accion}_")]


def confirmar_propuestas(at: AppTest) -> AppTest:
    """Click «Confirmar» on every pending propuesta of the agent, one by one."""

    while botones := botones_propuesta(at):
        at = botones[0].click().run()
    return at


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
    monkeypatch.setattr(AppTest, "_run", _run_siguiendo_la_pagina(AppTest._run))
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
