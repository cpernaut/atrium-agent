import pytest

from atrium.rag import classify


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("¿Cuál es la altura máxima permitida en una vivienda?", "normativa"),
        ("¿Qué dice la ordenanza sobre el FOT?", "normativa"),
        ("¿Qué materiales de fachada me conviene usar?", "diseno"),
        ("Ideas para la distribución de ambientes con luz natural", "diseno"),
        ("Hola, ¿cómo estás?", "general"),
    ],
)
def test_classify(question, expected):
    assert classify({"mensajes": [question]})["category"] == expected


def test_classify_uses_last_message():
    state = {"mensajes": ["hola", "¿altura máxima?"]}
    assert classify(state)["category"] == "normativa"
