"""«Esquema aplicado» check for the auto-merge (run by listo-para-mergear.yml).

Merging to main deploys the app, but supabase_schema.sql is not applied by
itself. If the PR changes it, the check fails until the PR has the label
«esquema aplicado» (put after running the schema in Supabase). A new push that
changes the schema again removes the label: the schema must be run again.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ESQUEMA = "supabase_schema.sql"
ETIQUETA = "esquema aplicado"


def decidir(
    cambia_esquema: bool, etiquetas: list[str], push_cambia_esquema: bool
) -> tuple[bool, bool, str]:
    """(passes, remove_label, message). Pure, so it can be tested."""

    if not cambia_esquema:
        return True, False, "El PR no cambia supabase_schema.sql."
    if ETIQUETA in etiquetas and push_cambia_esquema:
        return (
            False,
            True,
            "Un commit nuevo cambió supabase_schema.sql después de aplicarlo: se quitó la "
            f"etiqueta «{ETIQUETA}». Volvé a correr el esquema en Supabase y ponela de nuevo.",
        )
    if ETIQUETA in etiquetas:
        return True, False, f"Cambia el esquema y tiene la etiqueta «{ETIQUETA}»."
    return (
        False,
        False,
        f"Este PR cambia {ESQUEMA}. Antes de mergear: correr el esquema en Supabase y "
        f"ponerle al PR la etiqueta «{ETIQUETA}».",
    )


def _gh(*args: str) -> str:
    return subprocess.run(["gh", "api", *args], check=True, capture_output=True, text=True).stdout


def main() -> int:
    evento = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    repo = os.environ["GITHUB_REPOSITORY"]
    pr = evento["pull_request"]
    archivos = _gh(
        "--paginate", f"repos/{repo}/pulls/{pr['number']}/files", "--jq", ".[].filename"
    ).split()
    push_cambia = False
    if evento.get("action") == "synchronize" and evento.get("before"):
        cambiados = _gh(
            f"repos/{repo}/compare/{evento['before']}...{evento['after']}",
            "--jq",
            ".files[].filename",
        ).split()
        push_cambia = ESQUEMA in cambiados
    etiquetas = [e["name"] for e in pr.get("labels", [])]

    pasa, quitar, mensaje = decidir(ESQUEMA in archivos, etiquetas, push_cambia)
    if quitar:
        _gh("-X", "DELETE", f"repos/{repo}/issues/{pr['number']}/labels/{quote(ETIQUETA)}")
    print(mensaje if pasa else f"::error::{mensaje}")
    return 0 if pasa else 1


if __name__ == "__main__":
    sys.exit(main())
