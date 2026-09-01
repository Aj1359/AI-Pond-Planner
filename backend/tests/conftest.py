"""
Pytest configuration and shared test fixtures.
Provides an in-memory FakeSupabase client fixture so tests can run without real cloud DB credentials.
"""
import pytest
from unittest.mock import MagicMock


class FakePostgrestQuery:
    def __init__(self, table_name: str, tables_store: dict):
        self.table_name = table_name
        self.tables_store = tables_store
        self._action = "select"
        self._payload = None
        self._filters = []
        self._in_filters = []
        self._order_col = None
        self._order_desc = False

    def select(self, *args, **kwargs):
        self._action = "select"
        return self

    def insert(self, data, *args, **kwargs):
        self._action = "insert"
        self._payload = data if isinstance(data, list) else [data]
        return self

    def update(self, data, *args, **kwargs):
        self._action = "update"
        self._payload = data
        return self

    def delete(self, *args, **kwargs):
        self._action = "delete"
        return self

    def upsert(self, data, on_conflict=None, *args, **kwargs):
        self._action = "upsert"
        self._payload = data if isinstance(data, list) else [data]
        return self

    def eq(self, column: str, value):
        self._filters.append((column, value))
        return self

    def in_(self, column: str, values: list):
        self._in_filters.append((column, values))
        return self

    def order(self, column: str, desc: bool = False):
        self._order_col = column
        self._order_desc = desc
        return self

    def execute(self):
        table_rows = self.tables_store.setdefault(self.table_name, [])

        if self._action == "insert":
            inserted = []
            for item in self._payload:
                row = dict(item)
                if "id" not in row:
                    row["id"] = len(table_rows) + 1
                table_rows.append(row)
                inserted.append(row)
            res = MagicMock()
            res.data = inserted
            return res

        elif self._action == "upsert":
            upserted = []
            for item in self._payload:
                row = dict(item)
                # Check for existing match based on unique fields
                match_idx = None
                for i, existing in enumerate(table_rows):
                    if "name" in row and existing.get("name") == row["name"]:
                        match_idx = i
                        break
                    elif "village_id" in row and "candidate_id" in row:
                        if existing.get("village_id") == row["village_id"] and existing.get("candidate_id") == row["candidate_id"]:
                            match_idx = i
                            break
                    elif "village_id" in row and "source" in row and "resolution_m" in row:
                        if existing.get("village_id") == row["village_id"]:
                            match_idx = i
                            break
                    elif "candidate_site_id" in row:
                        if existing.get("candidate_site_id") == row["candidate_site_id"]:
                            match_idx = i
                            break

                if match_idx is not None:
                    table_rows[match_idx].update(row)
                    upserted.append(table_rows[match_idx])
                else:
                    if "id" not in row:
                        row["id"] = len(table_rows) + 1
                    table_rows.append(row)
                    upserted.append(row)
            res = MagicMock()
            res.data = upserted
            return res

        elif self._action == "update":
            updated = []
            for row in table_rows:
                match = all(row.get(col) == val for col, val in self._filters)
                if match:
                    row.update(self._payload)
                    updated.append(row)
            res = MagicMock()
            res.data = updated
            return res

        elif self._action == "delete":
            deleted = []
            remaining = []
            for row in table_rows:
                match = all(row.get(col) == val for col, val in self._filters)
                if match:
                    deleted.append(row)
                else:
                    remaining.append(row)
            self.tables_store[self.table_name] = remaining
            res = MagicMock()
            res.data = deleted
            return res

        else:  # select
            filtered = []
            for row in table_rows:
                match = True
                for col, val in self._filters:
                    if row.get(col) != val:
                        match = False
                        break
                for col, vals in self._in_filters:
                    if row.get(col) not in vals:
                        match = False
                        break
                if match:
                    filtered.append(dict(row))

            if self._order_col:
                filtered.sort(key=lambda x: x.get(self._order_col, 0), reverse=self._order_desc)

            res = MagicMock()
            res.data = filtered
            return res


class FakeSupabaseClient:
    def __init__(self):
        self.tables = {}

    def table(self, table_name: str):
        return FakePostgrestQuery(table_name, self.tables)


@pytest.fixture
def fake_supabase(monkeypatch):
    client = FakeSupabaseClient()
    from app import db
    monkeypatch.setattr(db, "get_client", lambda: client)
    return client
