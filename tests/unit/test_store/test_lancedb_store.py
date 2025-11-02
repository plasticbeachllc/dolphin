"""Unit tests for LanceDBStore operations with mocks."""

import types
import pytest
from pathlib import Path

from kb.store.lancedb_store import LanceDBStore


class _MockTable:
    def __init__(self, name: str):
        self.name = name
        self.rows = []
        self.deleted_ids = []

    def delete(self, filter_expr: str):
        # Naive delete: parse id in ('a','b',...)
        if "in (" in filter_expr:
            inside = filter_expr.split("in (", 1)[1].rsplit(")", 1)[0]
            ids = [s.strip().strip("'") for s in inside.split(",") if s.strip()]
            self.deleted_ids.extend(ids)
            self.rows = [r for r in self.rows if r.get("id") not in ids]

    def add(self, rows):
        self.rows.extend(list(rows))


class _MockDB:
    def __init__(self):
        self._tables: dict[str, _MockTable] = {}

    def table_names(self):
        return list(self._tables.keys())

    def create_table(self, name, data=None, schema=None):
        self._tables[name] = _MockTable(name)
        return self._tables[name]

    def open_table(self, name):
        if name not in self._tables:
            raise RuntimeError(f"Table {name} not found")
        return self._tables[name]


@pytest.fixture
def mocked_lancedb(monkeypatch):
    import sys
    mock_mod = types.SimpleNamespace()
    db = _MockDB()

    def connect(path: str):
        _ = path
        return db

    mock_mod.connect = connect
    # Ensure `import lancedb` in code under test resolves to our mock
    monkeypatch.setitem(sys.modules, "lancedb", mock_mod)
    return db


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path / "lancedb"


def test_initialize_collections_creates_tables(monkeypatch, mocked_lancedb, tmp_root):
    store = LanceDBStore(tmp_root)

    # Mock pyarrow presence without heavy import
    import sys
    fake_pa = types.SimpleNamespace(
        field=lambda *args, **kwargs: object(),
        schema=lambda fields: object(),
        list_=lambda t, size=None: t,  # Accept optional size parameter for fixed-size lists
        float32=lambda: object(),
        string=lambda: object(),
        int32=lambda: object(),
        timestamp=lambda *args, **kwargs: object(),
    )
    monkeypatch.setitem(sys.modules, "pyarrow", fake_pa)

    store.initialize_collections()
    assert set(mocked_lancedb.table_names()) == {"chunks_small", "chunks_large"}


def test_upsert_chunks_validates_vector_dims(mocked_lancedb, tmp_root):
    store = LanceDBStore(tmp_root)
    # Pre-create tables
    mocked_lancedb.create_table("chunks_small")
    mocked_lancedb.create_table("chunks_large")

    # Wrong dim for small
    with pytest.raises(ValueError):
        store.upsert_chunks(
            "repo",
            [{"id": "1", "vector": [0.0] * 10}],
            model="small",
        )

    # Correct dims should pass and write rows
    vec = [0.0] * 1536
    store.upsert_chunks(
        "repo",
        [
            {"id": "a", "vector": vec},
            {"id": "b", "vector": vec},
        ],
        model="small",
    )
    tbl = mocked_lancedb.open_table("chunks_small")
    assert {r["id"] for r in tbl.rows} == {"a", "b"}


def test_upsert_chunks_creates_table_on_missing(mocked_lancedb, tmp_root):
    store = LanceDBStore(tmp_root)
    vec = [0.0] * 1536
    # No pre-created table. First attempt should create and retry.
    store.upsert_chunks(
        "repo",
        [{"id": "x", "vector": vec}],
        model="small",
    )
    assert "chunks_small" in mocked_lancedb.table_names()
    assert mocked_lancedb.open_table("chunks_small").rows[0]["id"] == "x"


def test_query_returns_empty(tmp_root):
    store = LanceDBStore(tmp_root)
    results = store.query([0.0] * 1536, repo=None, top_k=5)
    assert results == []
