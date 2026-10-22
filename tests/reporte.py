"""Readable test report: what each case checks and how it went.

pytest hooks (wired in ``tests/conftest.py``) that, at the end of the run, write:

- a Markdown summary to ``$GITHUB_STEP_SUMMARY`` (the «Summary» page of a
  GitHub Actions run), and
- ``reporte-tests.html`` in ``$TEST_REPORT_DIR`` (uploaded as an artifact).

Nothing is written when neither variable is set, so local runs stay quiet.

Each row uses the test's docstring: the case ID (``F-03-CA-29``, ``E2E-04``,
``LIVE-13``…) and the sentence that says what it checks, so the report always
matches the code. Cases with an ID are listed one by one; the rest (unit tests)
are counted per area, and listed only if they fail.
"""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from pathlib import Path

# Case IDs from the fichas and docs/casos-e2e.md, at the start of the docstring.
_ID = re.compile(r"^((?:F-\d{2}-)?(?:CA|SEG|A11Y)-\d+[a-z]?|E2E-\d+|LIVE-\d+)\b")
_SEPARADORES = re.compile(r"^[\s:/(),·—-]+")

AREAS = (
    ("tests/e2e/test_app_flows.py", "App: acceso, obras y agente"),
    ("tests/e2e/test_plata_flows.py", "Presupuesto y gastos"),
    ("tests/e2e/test_presupuesto_flows.py", "Ítems del presupuesto"),
    ("tests/live/", "Base real (Supabase)"),
)
UNITARIOS = "Unitarios"
ICONOS = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}
PALABRAS = {"passed": "Pasó", "failed": "Falló", "skipped": "Salteado"}


@dataclass
class Caso:
    nodeid: str
    area: str
    id: str | None
    que_prueba: str
    variante: str | None = None
    resultado: str | None = None
    detalle: str = ""


_casos: dict[str, Caso] = {}


def _area(nodeid: str) -> str:
    return next((nombre for ruta, nombre in AREAS if nodeid.startswith(ruta)), UNITARIOS)


def _descripcion(item) -> tuple[str | None, str]:
    """(case ID, what it checks) from the docstring; the test name if there is none."""

    doc = getattr(getattr(item, "function", None), "__doc__", None) or ""
    parrafo = " ".join(doc.strip().split("\n\n")[0].split())
    nombre = item.originalname.removeprefix("test_").replace("_", " ")
    nombre = nombre[:1].upper() + nombre[1:]
    if not parrafo:
        return None, nombre
    coincide = _ID.match(parrafo)
    if not coincide:
        return None, parrafo
    resto = parrafo[coincide.end() :]
    # «LIVE-13 (F-03-CA-13): …» or «F-03-CA-26 / R16: …»: skip the references.
    resto = re.sub(r"^\s*(\([^)]*\)|/\s*[A-Z0-9-]+)\s*", "", resto)
    resto = _SEPARADORES.sub("", resto).strip()
    if len(resto.strip(" .")) < 3:  # «F-03-CA-3 (dominio).»: the test name says more
        resto = nombre
    return coincide.group(1), resto[:1].upper() + resto[1:]


def _corto(valor, maximo: int = 40) -> str:
    texto = str(valor)
    return texto if len(texto) <= maximo else texto[: maximo - 1] + "…"


def registrar_items(items) -> None:
    for item in items:
        id_, que = _descripcion(item)
        params = getattr(getattr(item, "callspec", None), "params", None)
        variante = ", ".join(_corto(v) for v in params.values()) if params else None
        _casos[item.nodeid] = Caso(item.nodeid, _area(item.nodeid), id_, que, variante)


def _motivo(report) -> str:
    if report.skipped and isinstance(report.longrepr, tuple):
        return str(report.longrepr[2]).removeprefix("Skipped: ")
    crash = getattr(report.longrepr, "reprcrash", None)
    texto = crash.message if crash else str(report.longrepr or "")
    return texto.strip().splitlines()[0][:240] if texto.strip() else ""


def registrar_resultado(report) -> None:
    caso = _casos.get(report.nodeid)
    if caso is None:
        return
    if report.failed:
        caso.resultado, caso.detalle = "failed", _motivo(report)
    elif report.skipped and caso.resultado is None:
        caso.resultado, caso.detalle = "skipped", _motivo(report)
    elif report.when == "call" and report.passed and caso.resultado is None:
        caso.resultado = "passed"


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _por_area() -> dict[str, list[Caso]]:
    grupos: dict[str, list[Caso]] = {}
    for caso in _casos.values():
        if caso.resultado:
            grupos.setdefault(caso.area, []).append(caso)
    orden = [nombre for _, nombre in AREAS] + [UNITARIOS]
    return {a: grupos[a] for a in orden if a in grupos}


def _cuenta(casos: list[Caso], resultado: str) -> int:
    return sum(c.resultado == resultado for c in casos)


def _filas(casos: list[Caso]) -> list[Caso]:
    """Cases listed one by one: those with an ID, and any failure."""

    todos_salteados = all(c.resultado == "skipped" for c in casos)
    return [
        c
        for c in casos
        if c.resultado == "failed"
        # Unit tests are only counted (the HTML lists them all), unless they fail.
        or (c.id and c.area != UNITARIOS and not todos_salteados)
    ]


def _celda(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def markdown(titulo: str) -> str:
    grupos = _por_area()
    todos = [c for casos in grupos.values() for c in casos]
    fallidos = _cuenta(todos, "failed")
    estado = "❌ Hay tests que fallaron" if fallidos else "✅ Todo pasó"
    lineas = [
        f"## {titulo}",
        "",
        f"**{estado}** · {_cuenta(todos, 'passed')} pasaron · {fallidos} fallaron · "
        f"{_cuenta(todos, 'skipped')} salteados",
        "",
        "| Área | Total | ✅ Pasaron | ❌ Fallaron | ⏭️ Salteados |",
        "|---|---|---|---|---|",
    ]
    for area, casos in grupos.items():
        lineas.append(
            f"| {area} | {len(casos)} | {_cuenta(casos, 'passed')} | "
            f"{_cuenta(casos, 'failed')} | {_cuenta(casos, 'skipped')} |"
        )
    for area, casos in grupos.items():
        filas = _filas(casos)
        salteados = [c for c in casos if c.resultado == "skipped"]
        if not filas and len(salteados) == len(casos):
            lineas += ["", f"### {area}", "", f"⏭️ Salteados: {_celda(salteados[0].detalle)}"]
            continue
        if not filas:
            continue
        lineas += ["", f"### {area}", "", "| | ID | Qué prueba | Resultado |", "|---|---|---|---|"]
        for c in filas:
            que = c.que_prueba + (f" *({c.variante})*" if c.variante else "")
            resultado = PALABRAS[c.resultado] + (f": {c.detalle}" if c.detalle else "")
            lineas.append(
                f"| {ICONOS[c.resultado]} | {c.id or '—'} | {_celda(que)} | {_celda(resultado)} |"
            )
    lineas.append("")
    return "\n".join(lineas)


def html_reporte(titulo: str) -> str:
    e = html.escape
    grupos = _por_area()
    partes = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>{e(titulo)}</title><style>",
        "body{font-family:system-ui,sans-serif;margin:16px;color:#222;background:#fff}",
        "table{border-collapse:collapse;width:100%;margin:8px 0 24px}",
        "th,td{border:1px solid #ccc;padding:6px 8px;text-align:left;vertical-align:top}",
        "th{background:#f3f3f3}.failed{background:#fde8e8}",
        "</style></head><body>",
        f"<h1>{e(titulo)}</h1>",
    ]
    for area, casos in grupos.items():
        partes.append(
            f"<h2>{e(area)}</h2><p>✅ {_cuenta(casos, 'passed')} pasaron · "
            f"❌ {_cuenta(casos, 'failed')} fallaron · ⏭️ {_cuenta(casos, 'skipped')} salteados</p>"
        )
        partes.append("<table><tr><th></th><th>ID</th><th>Qué prueba</th><th>Resultado</th></tr>")
        for c in casos:  # the HTML lists every test
            que = c.que_prueba + (f" ({c.variante})" if c.variante else "")
            resultado = PALABRAS[c.resultado] + (f": {c.detalle}" if c.detalle else "")
            partes.append(
                f"<tr class='{c.resultado}'><td>{ICONOS[c.resultado]}</td><td>{e(c.id or '—')}</td>"
                f"<td>{e(que)}</td><td>{e(resultado)}</td></tr>"
            )
        partes.append("</table>")
    partes.append("</body></html>")
    return "\n".join(partes)


def escribir() -> None:
    resumen = os.getenv("GITHUB_STEP_SUMMARY")
    carpeta = os.getenv("TEST_REPORT_DIR")
    if not (resumen or carpeta) or not _por_area():
        return
    titulo = os.getenv("TEST_REPORT_TITLE", "Resultado de los tests")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as archivo:
            archivo.write(markdown(titulo))
    if carpeta:
        Path(carpeta).mkdir(parents=True, exist_ok=True)
        (Path(carpeta) / "reporte-tests.html").write_text(html_reporte(titulo), encoding="utf-8")
