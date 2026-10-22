"""The readable test report (tests/reporte.py)."""

from types import SimpleNamespace

import pytest

from tests import reporte


def _item(doc, nombre="test_algo", nodeid="tests/e2e/test_plata_flows.py::test_algo"):
    def funcion():
        pass

    funcion.__doc__ = doc
    return SimpleNamespace(function=funcion, originalname=nombre, nodeid=nodeid)


@pytest.mark.parametrize(
    "doc, esperado",
    [
        ("F-03-CA-29: anular pide confirmación.", ("F-03-CA-29", "Anular pide confirmación.")),
        ("LIVE-13 (F-03-CA-13): sin login no se ve nada.", ("LIVE-13", "Sin login no se ve nada.")),
        ("F-03-CA-26 / R16: semáforo por ítem.", ("F-03-CA-26", "Semáforo por ítem.")),
        ("E2E-04: crea una obra.\n\n    Detalle técnico.", ("E2E-04", "Crea una obra.")),
        ("F-03-CA-3 (dominio).", ("F-03-CA-3", "Algo")),
        ("Revisión PR #5: no se corta.", (None, "Revisión PR #5: no se corta.")),
        (None, (None, "Algo")),
    ],
)
def test_id_y_que_prueba_salen_del_docstring(doc, esperado):
    assert reporte._descripcion(_item(doc)) == esperado


def test_markdown_con_un_fallo_y_salteados(monkeypatch):
    monkeypatch.setattr(reporte, "_casos", {})
    reporte._casos.update(
        {
            "a": reporte.Caso(
                "a", "Presupuesto y gastos", "F-03-CA-1", "Uno | dos", None, "passed"
            ),
            "b": reporte.Caso("b", "Unitarios", None, "Interno", None, "passed"),
            "c": reporte.Caso("c", "Unitarios", None, "Roto", None, "failed", "AssertionError: x"),
            "d": reporte.Caso(
                "d", "Base real (Supabase)", "LIVE-1", "Y", None, "skipped", "faltan"
            ),
        }
    )
    texto = reporte.markdown("Título")

    assert "**❌ Hay tests que fallaron** · 2 pasaron · 1 fallaron · 1 salteados" in texto
    assert "| ✅ | F-03-CA-1 | Uno \\| dos | Pasó |" in texto  # escapa el separador
    assert "| ❌ | — | Roto | Falló: AssertionError: x |" in texto
    assert "Interno" not in texto  # los unitarios que pasan solo se cuentan
    assert "⏭️ Salteados: faltan" in texto
    assert "<td>Interno</td>" in reporte.html_reporte("Título")  # el HTML lista todo


def test_sin_variables_no_escribe_nada(monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("TEST_REPORT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    reporte.escribir()
    assert list(tmp_path.iterdir()) == []
