"""«Esquema aplicado» check for the auto-merge (run by listo-para-mergear.yml).

Merging to main deploys the app, but supabase_schema.sql is not applied by
itself. If the PR changes it, the check fails until the PR has the label
«esquema aplicado» (put after running the schema in Supabase).

The label is bound to the exact content of the schema: when it is added, the
check records the git blob SHA of supabase_schema.sql at the PR head in a bot
comment. Every run compares that SHA with the schema at the current head; if
they differ (a new commit, a force-push, a revert), the label is removed and the
check fails. The order in which GitHub delivers events doesn't matter.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ESQUEMA = "supabase_schema.sql"
ETIQUETA = "esquema aplicado"
MARCA = re.compile(r"<!-- esquema-aplicado:([0-9a-f]{40}) -->")
BOT = "github-actions[bot]"


def toca_esquema(archivos: list[dict]) -> bool:
    """Whether the PR changes the schema: edited, added, deleted or renamed (either way)."""

    return any(ESQUEMA in (a.get("filename"), a.get("previous_filename")) for a in archivos)


def decidir(
    cambia_esquema: bool,
    tiene_etiqueta: bool,
    recien_etiquetado: bool,
    confirmado: str | None,
    actual: str | None,
    etiquetado: str | None = None,
) -> tuple[bool, str]:
    """(passes, action) where action is "", "registrar" or "quitar". Pure, tested.

    ``actual``: schema blob SHA at the PR head now. ``etiquetado``: at the commit
    the PR had when the label was added (the event's head). ``None`` means it
    couldn't be read (API error, file deleted): never approves.
    """

    if not cambia_esquema:
        return True, ""
    if not tiene_etiqueta:
        return False, ""
    if actual is None:
        return False, "quitar"  # can't verify the schema: never approve
    if recien_etiquetado:
        # The label confirms the schema of the commit that was labeled; a push that
        # arrived before this run (another schema) doesn't get confirmed by it.
        if etiquetado is not None and etiquetado == actual:
            return True, "registrar"
        return False, "quitar"
    if confirmado is None:
        # Labeled, but the «labeled» run hasn't recorded it yet (events can arrive
        # out of order): wait for it instead of removing a valid label.
        return False, ""
    if confirmado == actual:
        return True, ""
    return False, "quitar"  # the schema changed since it was confirmed


MENSAJES = {
    (True, ""): "Listo: el esquema de este PR está confirmado como aplicado (o no cambia).",
    (True, "registrar"): "Esquema confirmado como aplicado tal como está en este commit.",
    (False, ""): (
        f"Este PR cambia {ESQUEMA}. Antes de mergear: correr el esquema en Supabase y "
        f"ponerle al PR la etiqueta «{ETIQUETA}» (si ya la tiene, se está registrando)."
    ),
    (False, "quitar"): (
        f"{ESQUEMA} cambió desde que se confirmó: se quitó la etiqueta «{ETIQUETA}». "
        "Volvé a correr el esquema en Supabase y ponela de nuevo."
    ),
}


def _gh(*args: str, check: bool = True) -> str:
    resultado = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if check and resultado.returncode:
        raise RuntimeError(resultado.stderr.strip())
    return resultado.stdout if not resultado.returncode else ""


def main() -> int:
    evento = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    repo = os.environ["GITHUB_REPOSITORY"]
    numero = evento["pull_request"]["number"]
    # Fresh data, not the event payload: events can arrive out of order.
    pr = json.loads(_gh(f"repos/{repo}/pulls/{numero}"))
    head = pr["head"]["sha"]
    archivos = [
        archivo
        for pagina in json.loads(
            _gh("--paginate", "--slurp", f"repos/{repo}/pulls/{numero}/files") or "[]"
        )
        for archivo in pagina
    ]

    def blob(ref: str) -> str | None:
        sha = _gh(f"repos/{repo}/contents/{ESQUEMA}?ref={ref}", "--jq", ".sha", check=False)
        return sha.strip() if re.fullmatch(r"[0-9a-f]{40}", sha.strip()) else None

    actual = blob(head)
    etiquetas = [e["name"] for e in pr.get("labels", [])]
    recien = (
        evento.get("action") == "labeled"
        and evento.get("label", {}).get("name") == ETIQUETA
        and ETIQUETA in etiquetas
    )
    confirmado = None
    comentarios = json.loads(
        _gh("--paginate", "--slurp", f"repos/{repo}/issues/{numero}/comments") or "[]"
    )
    for pagina in comentarios:
        for c in pagina:
            marca = MARCA.search(c.get("body") or "")
            if marca and c.get("user", {}).get("login") == BOT:
                confirmado = marca.group(1)  # the last one wins

    etiquetado = blob(evento["pull_request"]["head"]["sha"]) if recien else None
    pasa, accion = decidir(
        toca_esquema(archivos), ETIQUETA in etiquetas, recien, confirmado, actual, etiquetado
    )
    if accion == "registrar" and actual:
        _gh(
            "-X",
            "POST",
            f"repos/{repo}/issues/{numero}/comments",
            "-f",
            f"body=<!-- esquema-aplicado:{actual} -->✅ Esquema confirmado como aplicado "
            f"en Supabase para `{ESQUEMA}` en {head[:7]}. Si vuelve a cambiar, hay que "
            "correrlo de nuevo.",
        )
    if accion == "quitar":
        _gh("-X", "DELETE", f"repos/{repo}/issues/{numero}/labels/{quote(ETIQUETA)}", check=False)
    mensaje = MENSAJES[(pasa, accion)]
    print(mensaje if pasa else f"::error::{mensaje}")
    return 0 if pasa else 1


if __name__ == "__main__":
    sys.exit(main())
