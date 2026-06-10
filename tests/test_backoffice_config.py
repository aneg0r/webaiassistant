"""Tests for backoffice configuration API and store."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture
def backoffice_dirs(tmp_path, monkeypatch):
    bo = tmp_path / "backoffice"
    scen = bo / "scenarii"
    scen.mkdir(parents=True)
    (bo / "faq.json").write_text(
        json.dumps([{"question": "Q1", "answer": "A1"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (scen / "test_scenario.md").write_text("# Test\n", encoding="utf-8")
    monkeypatch.setattr(config, "BACKOFFICE_DIR", bo)
    monkeypatch.setattr(config, "SCENARII_DIR", scen)
    import app.backoffice_store as store

    monkeypatch.setattr(store, "_FAQ_PATH", bo / "faq.json")
    monkeypatch.setattr(store, "_SCENARII_DIR", scen)
    return bo, scen


@pytest.fixture
def client():
    return TestClient(app)


def test_read_write_faq(backoffice_dirs) -> None:
    from app import backoffice_store

    entries = backoffice_store.read_faq()
    assert entries == [{"question": "Q1", "answer": "A1"}]
    backoffice_store.write_faq(
        [{"question": "N", "answer": "O"}, {"question": " ", "answer": " "}]
    )
    assert len(backoffice_store.read_faq()) == 2


def test_faq_validation(backoffice_dirs) -> None:
    from app import backoffice_store

    with pytest.raises(ValueError, match="array"):
        backoffice_store.validate_faq_payload({})
    with pytest.raises(ValueError, match="question"):
        backoffice_store.validate_faq_payload([{"question": 1, "answer": "x"}])


def test_scenario_path_traversal(backoffice_dirs) -> None:
    from app import backoffice_store

    with pytest.raises(ValueError):
        backoffice_store.read_scenario_file("../faq.json")
    with pytest.raises(ValueError):
        backoffice_store.write_scenario_file("bad.txt", "x")


def test_api_faq_roundtrip(backoffice_dirs, client) -> None:
    r = client.get("/backoffice/faq")
    assert r.status_code == 200
    assert r.json()["entries"][0]["question"] == "Q1"

    r = client.put(
        "/backoffice/faq",
        json={"entries": [{"question": "Q2", "answer": "A2"}]},
    )
    assert r.status_code == 200
    assert r.json()["entries"][0]["question"] == "Q2"


def test_ensure_faq_from_example_copies_when_missing(tmp_path, monkeypatch) -> None:
    from app import backoffice_store

    bo = tmp_path / "backoffice"
    bo.mkdir()
    example = tmp_path / "faq.json.example"
    example.write_text(
        json.dumps([{"question": "Q?", "answer": "A."}], ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "BACKOFFICE_DIR", bo)
    monkeypatch.setattr(backoffice_store, "_FAQ_PATH", bo / "faq.json")
    monkeypatch.setattr(backoffice_store, "_FAQ_EXAMPLE_PATH", example)

    backoffice_store.ensure_faq_from_example()

    assert (bo / "faq.json").is_file()
    assert backoffice_store.read_faq() == [{"question": "Q?", "answer": "A."}]


def test_ensure_faq_from_example_does_not_overwrite(tmp_path, monkeypatch) -> None:
    from app import backoffice_store

    bo = tmp_path / "backoffice"
    bo.mkdir()
    faq_path = bo / "faq.json"
    faq_path.write_text(
        json.dumps([{"question": "Existing", "answer": "Keep"}], ensure_ascii=False),
        encoding="utf-8",
    )
    example = tmp_path / "faq.json.example"
    example.write_text(
        json.dumps([{"question": "New", "answer": "Replace"}], ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "BACKOFFICE_DIR", bo)
    monkeypatch.setattr(backoffice_store, "_FAQ_PATH", faq_path)
    monkeypatch.setattr(backoffice_store, "_FAQ_EXAMPLE_PATH", example)

    backoffice_store.ensure_faq_from_example()

    assert backoffice_store.read_faq() == [{"question": "Existing", "answer": "Keep"}]


def test_ensure_wiki_from_example_copies_when_missing(tmp_path, monkeypatch) -> None:
    from app import backoffice_store

    bo = tmp_path / "backoffice"
    bo.mkdir()
    example = tmp_path / "wiki.md.example"
    example.write_text("# Wiki\n", encoding="utf-8")
    monkeypatch.setattr(config, "BACKOFFICE_DIR", bo)
    monkeypatch.setattr(backoffice_store, "_WIKI_PATH", bo / "wiki.md")
    monkeypatch.setattr(backoffice_store, "_WIKI_EXAMPLE_PATH", example)

    backoffice_store.ensure_wiki_from_example()

    assert (bo / "wiki.md").is_file()
    assert (bo / "wiki.md").read_text(encoding="utf-8") == "# Wiki\n"


def test_ensure_wiki_from_example_does_not_overwrite(tmp_path, monkeypatch) -> None:
    from app import backoffice_store

    bo = tmp_path / "backoffice"
    bo.mkdir()
    wiki_path = bo / "wiki.md"
    wiki_path.write_text("# Existing\n", encoding="utf-8")
    example = tmp_path / "wiki.md.example"
    example.write_text("# New\n", encoding="utf-8")
    monkeypatch.setattr(config, "BACKOFFICE_DIR", bo)
    monkeypatch.setattr(backoffice_store, "_WIKI_PATH", wiki_path)
    monkeypatch.setattr(backoffice_store, "_WIKI_EXAMPLE_PATH", example)

    backoffice_store.ensure_wiki_from_example()

    assert wiki_path.read_text(encoding="utf-8") == "# Existing\n"


def test_api_scenario_roundtrip(backoffice_dirs, client) -> None:
    r = client.get("/backoffice/scenarii/list")
    assert r.status_code == 200
    assert "test_scenario.md" in r.json()["files"]

    r = client.get("/backoffice/scenarii/file?file=test_scenario.md")
    assert r.status_code == 200
    assert "# Test" in r.json()["content"]

    r = client.put(
        "/backoffice/scenarii/file?file=test_scenario.md",
        json={"content": "# Updated\n"},
    )
    assert r.status_code == 200
    assert "Updated" in r.json()["content"]
