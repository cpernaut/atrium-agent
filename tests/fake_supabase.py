"""A tiny in-memory stand-in for the Supabase query builder used by atrium.obras."""

from __future__ import annotations

import copy
import itertools
from types import SimpleNamespace


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
                row = {"id": next(self.db.ids), "created_at": f"t{len(rows):04d}", **item}
                row.setdefault("avance", 0)
                row.setdefault("estado", "Planificación")
                rows.append(row)
                new.append(copy.deepcopy(row))
            return SimpleNamespace(data=new)
        matched = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for row in matched:
                row.update(self.payload)
            return SimpleNamespace(data=copy.deepcopy(matched))
        for col, desc in reversed(self.orders):
            matched.sort(key=lambda r, c=col: str(r.get(c) or ""), reverse=desc)
        return SimpleNamespace(data=copy.deepcopy(matched[: self.max_rows]))


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.ids = itertools.count(1)
        self.fail: str | None = None

    def table(self, name):
        return _Query(self, name)
