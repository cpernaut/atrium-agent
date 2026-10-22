"""The «Esquema aplicado» auto-merge check (.github/scripts/esquema_aplicado.py)."""

import importlib.util
from pathlib import Path

import pytest

_RUTA = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "esquema_aplicado.py"
_spec = importlib.util.spec_from_file_location("esquema_aplicado", _RUTA)
esquema_aplicado = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(esquema_aplicado)
decidir = esquema_aplicado.decidir


@pytest.mark.parametrize(
    "cambia, etiquetas, push, pasa, quitar",
    [
        (False, [], False, True, False),  # sin cambios de esquema: pasa
        (True, [], False, False, False),  # cambia el esquema: espera la etiqueta
        (True, ["esquema aplicado"], False, True, False),  # aplicado y etiquetado: pasa
        (True, ["esquema aplicado"], True, False, True),  # nuevo cambio: se quita la etiqueta
        (True, ["otra"], True, False, False),
    ],
)
def test_decidir(cambia, etiquetas, push, pasa, quitar):
    """AUTO-MERGE-1: el esquema confirmado se invalida si un commit nuevo lo cambia."""

    resultado = decidir(cambia, etiquetas, push)
    assert resultado[:2] == (pasa, quitar)
    assert resultado[2]
