"""Projects, film bible, persistence, and filesystem safety."""
from __future__ import annotations

import re

import pytest

from app.services.paths import safe_join, slugify
from app.services.projects import ProjectError


def test_slugify():
    assert slugify("Blue Horizon: A Film!") == "blue-horizon-a-film"
    assert slugify("!!!") == "untitled"


def test_safe_join_blocks_traversal(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError):
        safe_join(root, "..", "escape.md")
    with pytest.raises(ValueError):
        safe_join(root, "sub/../../evil.md")
    ok = safe_join(root, "bible", "film-bible.md")
    assert str(ok).startswith(str(root.resolve()))


def test_create_project_seeds_real_bible(tmp_path, client):
    resp = client.post("/api/v1/projects", data={"title": "Blue Horizon", "description": "ocean film"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "blue-horizon"

    docs = client.get(f"/api/v1/projects/{body['id']}/bible").json()["docs"]
    names = {d["name"] for d in docs}
    assert {
        "film-bible.md", "world.md", "characters.md", "visual-style.md",
        "continuity.md", "locations.md", "production-rules.md", "scene-index.md",
        "reference-index.md", "changelog.md",
    } <= names
    main = client.get(f"/api/v1/projects/{body['id']}/bible/film-bible.md").json()["content"]
    assert "Blue Horizon" in main
    assert "TO FILL" in main  # explicit placeholders, no invented lore
    assert "[TO FILL" in main


def test_bible_edit_persists_and_survives_restart(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from tests.conftest import make_settings

    app = create_app(make_settings(tmp_path))
    with TestClient(app) as c:
        pid = c.post("/api/v1/projects", data={"title": "Persist"}).json()["id"]
        content = c.get(f"/api/v1/projects/{pid}/bible/characters.md").json()["content"]
        content = content.replace("[TO FILL: Name]", "Mara the lighthouse keeper")
        put = c.put(f"/api/v1/projects/{pid}/bible/characters.md", json={"content": content})
        assert put.status_code == 200

    # restart
    app2 = create_app(make_settings(tmp_path))
    with TestClient(app2) as c2:
        pid2 = c2.get("/api/v1/projects").json()["projects"][0]["id"]
        after = c2.get(f"/api/v1/projects/{pid2}/bible/characters.md").json()["content"]
        assert "Mara the lighthouse keeper" in after


def test_bible_doc_name_traversal_rejected(client, project):
    for evil in ("../secrets.md", "film-bible.md/../../x", "UPPER.md", "a.md.exe", "new-doc.md"):
        resp = client.put(f"/api/v1/projects/{project['id']}/bible/{evil}", json={"content": "x"})
        assert resp.status_code in (400, 404), evil


def test_scenes_crud(client, project):
    resp = client.post(f"/api/v1/projects/{project['id']}/scenes", json={"title": "Opening Storm", "summary": "The fleet leaves"})
    assert resp.status_code == 201
    scene = resp.json()
    assert scene["slug"] == "opening-storm"
    scenes = client.get(f"/api/v1/projects/{project['id']}/scenes").json()["scenes"]
    assert len(scenes) == 1


def test_reference_upload_validation(client, project):
    import io
    from PIL import Image

    def png(w, h):
        buf = io.BytesIO()
        Image.new("RGB", (w, h)).save(buf, format="PNG")
        return buf.getvalue()

    # Too small (200px)
    r = client.post(
        f"/api/v1/projects/{project['id']}/references",
        files={"file": ("tiny.png", png(200, 200), "image/png")},
    )
    assert r.status_code == 400 and "dimensions" in r.json()["detail"]
    # Extreme aspect
    r = client.post(
        f"/api/v1/projects/{project['id']}/references",
        files={"file": ("wide.png", png(600, 6000), "image/png")},
    )
    assert r.status_code == 400
    # Disallowed mime
    r = client.post(
        f"/api/v1/projects/{project['id']}/references",
        files={"file": ("script.gif", b"GIF89a", "image/gif")},
    )
    assert r.status_code == 400 and "Unsupported file type" in r.json()["detail"]
    # Content/declared mismatch
    buf = io.BytesIO()
    Image.new("RGB", (640, 360)).save(buf, format="PNG")
    r = client.post(
        f"/api/v1/projects/{project['id']}/references",
        files={"file": ("fake.jpg", buf.getvalue(), "image/jpeg")},
    )
    assert r.status_code == 400 and "match" in r.json()["detail"]
    # Good upload with hostile filename
    r = client.post(
        f"/api/v1/projects/{project['id']}/references",
        files={"file": ("../../etc/passwd.png", png(640, 360), "image/png")},
        data={"role": "character", "entity_id": "char-001"},
    )
    assert r.status_code == 201
    asset = r.json()
    assert asset["filename"].startswith("ref_") and asset["filename"].endswith(".png")
    assert asset["original_filename"] == "passwd.png"
    assert asset["role"] == "character"
