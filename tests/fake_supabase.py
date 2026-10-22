"""A tiny in-memory stand-in for the Supabase query builder used by the domain."""

from __future__ import annotations

import copy
import itertools
from collections import defaultdict
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

# Column defaults from supabase_schema.sql, applied on insert like Postgres does.
_DEFAULTS = {
    "obras": {"estado": "Planificación", "moneda": "ARS", "avance": 0},
    "bitacora": {"fecha": date.today().isoformat()},
    "rubros": {"orden": 1000, "activo": True},
    "presupuesto_items": {"anulado": False},
    "gastos": {"anulado": False},
}


def _sort_key(value):
    """Numbers sort as numbers (like Postgres), everything else as text."""

    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return (0, value, "")
    return (1, 0, str(value or ""))


class _Query:
    def __init__(self, db: FakeSupabase, table: str):
        self.db, self.table_name = db, table
        self.filters: list = []
        self.orders: list = []
        self.max_rows: int | None = None
        self.op, self.payload = "select", None

    # builders -------------------------------------------------------------
    def select(self, *_):
        return self

    def eq(self, col, value):
        self.filters.append(lambda r: r.get(col) == value)
        return self

    def ilike(self, col, pattern):
        needle = pattern.strip("%").lower()
        self.filters.append(lambda r: needle in str(r.get(col) or "").lower())
        return self

    def order(self, col, desc=False):
        self.orders.append((col, desc))
        return self

    def limit(self, n):
        self.max_rows = n
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    # execution ------------------------------------------------------------
    def execute(self):
        if self.db.fail:
            raise RuntimeError(self.db.fail)
        rows = self.db.tables.setdefault(self.table_name, [])
        if self.op == "insert":
            new = []
            for item in self.payload if isinstance(self.payload, list) else [self.payload]:
                row = {"id": next(self.db.ids[self.table_name]), "created_at": f"t{len(rows):04d}"}
                row.update(_DEFAULTS.get(self.table_name, {}))
                row.update(item)
                rows.append(row)
                new.append(copy.deepcopy(row))
            return SimpleNamespace(data=new)
        matched = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for row in matched:
                row.update(self.payload)
            return SimpleNamespace(data=copy.deepcopy(matched))
        for col, desc in reversed(self.orders):
            matched.sort(key=lambda r, c=col: _sort_key(r.get(c)), reverse=desc)
        return SimpleNamespace(data=copy.deepcopy(matched[: self.max_rows]))


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.ids = defaultdict(lambda: itertools.count(1))  # one sequence per table
        self.fail: str | None = None

    def table(self, name):
        return _Query(self, name)


def seed_rubros(db: FakeSupabase) -> None:
    """The rubros precargados by supabase_schema.sql."""

    from atrium.finanzas import RUBROS_INICIALES

    for nombre, orden in RUBROS_INICIALES:
        db.table("rubros").insert({"nombre": nombre, "orden": orden}).execute()
