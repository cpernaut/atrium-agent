import pytest

from atrium.persistence import ChatMessage, PersistenceError, load_history, save_exchange


class FakeQuery:
    def __init__(self, table):
        self._table = table

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def order(self, *_):
        return self

    def insert(self, rows):
        if self._table.raise_on_write:
            raise RuntimeError("PGRST205: table not found")
        self._table.inserted.extend(rows)
        return self

    def execute(self):
        if self._table.raise_on_read:
            raise RuntimeError("network down")
        return type("Resp", (), {"data": self._table.rows})()


class FakeClient:
    def __init__(self, rows=None, raise_on_read=False, raise_on_write=False):
        self.rows = rows or []
        self.inserted = []
        self.raise_on_read = raise_on_read
        self.raise_on_write = raise_on_write

    def table(self, _name):
        return FakeQuery(self)


def test_load_history_maps_rows():
    client = FakeClient(
        rows=[
            {"rol": "user", "contenido": "hola"},
            {"rol": "assistant", "contenido": "buenas"},
        ]
    )
    assert load_history(client, "u1") == [
        ChatMessage("user", "hola"),
        ChatMessage("assistant", "buenas"),
    ]


def test_load_history_wraps_errors():
    with pytest.raises(PersistenceError):
        load_history(FakeClient(raise_on_read=True), "u1")


def test_save_exchange_writes_two_rows():
    client = FakeClient()
    save_exchange(client, "u1", "t1", "pregunta", "respuesta")
    assert [r["rol"] for r in client.inserted] == ["user", "assistant"]
    assert client.inserted[0]["contenido"] == "pregunta"
    assert client.inserted[1]["user_id"] == "u1"


def test_save_exchange_wraps_errors():
    with pytest.raises(PersistenceError):
        save_exchange(FakeClient(raise_on_write=True), "u1", "t1", "q", "a")
