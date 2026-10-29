"""Projects, film bible, and scenes — SQLite metadata + on-disk markdown structure.

Every project gets a real bible/ directory seeded from bible-templates/.
Bible documents are the canonical creative source of truth; the DB only
tracks project metadata (no bible duplication in the database).
"""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from app.config import REPO_ROOT
from app.services.paths import is_safe_doc_name, safe_join, slugify
from app.services.budget import iso, now_utc

TEMPLATE_DIR = REPO_ROOT / "bible-templates"
SUPPORTING_DIR = TEMPLATE_DIR / "supporting"

BIBLE_DOCS = (
    "film-bible.md",
    "world.md",
    "characters.md",
    "visual-style.md",
    "continuity.md",
    "locations.md",
    "production-rules.md",
    "scene-index.md",
    "reference-index.md",
    "changelog.md",
)

STATUS_VALUES = ("active", "paused", "archived")


class ProjectError(Exception):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class ProjectService:
    def __init__(self, conn: sqlite3.Connection, projects_root: Path) -> None:
        self.conn = conn
        self.root = projects_root

    # --- projects ----------------------------------------------------------
    def create_project(self, title: str, description: str = "") -> dict:
        title = title.strip()
        if not title or len(title) > 120:
            raise ProjectError("Title is required (max 120 chars).")
        slug = slugify(title)
        base, n = slug, 2
        while True:
            row = self.conn.execute("SELECT 1 FROM projects WHERE slug = ?", (slug,)).fetchone()
            if row is None:
                break
            slug = f"{base}-{n}"
            n += 1
        pid = new_id("prj")
        now = iso(now_utc())
        self.conn.execute(
            "INSERT INTO projects (id, slug, title, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 'active', ?, ?)",
            (pid, slug, title, description.strip(), now, now),
        )
        self.conn.commit()
        self._seed_project_dir(pid, slug, title)
        return self.get_project(pid)

    def _seed_project_dir(self, pid: str, slug: str, title: str) -> None:
        pdir = safe_join(self.root, slug)
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "references").mkdir(exist_ok=True)
        (pdir / "scenes").mkdir(exist_ok=True)
        (pdir / "generations").mkdir(exist_ok=True)
        bible = pdir / "bible"
        bible.mkdir(exist_ok=True)
        main = (TEMPLATE_DIR / "film-bible-template.md").read_text(encoding="utf-8")
        (bible / "film-bible.md").write_text(main.replace("{{TITLE}}", title), encoding="utf-8")
        for name in BIBLE_DOCS[1:]:
            body = (SUPPORTING_DIR / name).read_text(encoding="utf-8")
            (bible / name).write_text(body.replace("{{TITLE}}", title), encoding="utf-8")
        (pdir / "project.json").write_text(
            '{"id": "%s", "slug": "%s", "title": "%s"}' % (pid, slug, title.replace('"', "")),
            encoding="utf-8",
        )

    def _project_row(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d["scene_count"] = self.conn.execute(
            "SELECT COUNT(*) AS c FROM scenes WHERE project_id = ?", (d["id"],)
        ).fetchone()["c"]
        d["generation_count"] = self.conn.execute(
            "SELECT COUNT(*) AS c FROM generations WHERE project_id = ?", (d["id"],)
        ).fetchone()["c"]
        return d

    def get_project(self, pid: str) -> dict:
        row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        if row is None:
            raise ProjectError(f"Project {pid} not found", )
        return self._project_row(row)

    def get_project_by_slug(self, slug: str) -> str:
        row = self.conn.execute("SELECT id FROM projects WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            raise ProjectError(f"No project with slug {slug}")
        return row["id"]

    def list_projects(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [self._project_row(r) for r in rows]

    def update_project(self, pid: str, **fields) -> dict:
        allowed = {"title", "description", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "status" in updates and updates["status"] not in STATUS_VALUES:
            raise ProjectError(f"Invalid status {updates['status']}")
        if updates:
            sets = ", ".join(f"{k} = ?" for k in updates)
            self.conn.execute(
                f"UPDATE projects SET {sets}, updated_at = ? WHERE id = ?",
                (*updates.values(), iso(now_utc()), pid),
            )
            self.conn.commit()
        return self.get_project(pid)

    def delete_project(self, pid: str, delete_files: bool = False) -> None:
        project = self.get_project(pid)
        self.conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
        self.conn.commit()
        if delete_files:
            import shutil

            shutil.rmtree(safe_join(self.root, project["slug"]), ignore_errors=True)

    # --- bible ---------------------------------------------------------------
    def _bible_dir(self, pid: str) -> Path:
        project = self.get_project(pid)
        return safe_join(self.root, project["slug"], "bible")

    def list_bible_docs(self, pid: str) -> list[dict]:
        docs = []
        for name in BIBLE_DOCS:
            path = self._bible_dir(pid) / name
            docs.append(
                {
                    "name": name,
                    "canonical": name == "film-bible.md",
                    "exists": path.exists(),
                    "size_bytes": path.stat().st_size if path.exists() else 0,
                    "modified_at": iso(now_utc()) if path.exists() else None,
                }
            )
        return docs

    def read_bible_doc(self, pid: str, name: str) -> str:
        if not is_safe_doc_name(name):
            raise ProjectError("Invalid bible document name.")
        path = safe_join(self._bible_dir(pid), name)
        if not path.exists():
            raise ProjectError(f"Bible document {name} not found.")
        return path.read_text(encoding="utf-8")

    def write_bible_doc(self, pid: str, name: str, content: str) -> None:
        if not is_safe_doc_name(name) or name not in BIBLE_DOCS:
            raise ProjectError(f"Bible document {name} is not a recognized bible file.")
        if len(content) > 512_000:
            raise ProjectError("Bible document too large (max 512 KB).")
        path = safe_join(self._bible_dir(pid), name)
        path.write_text(content, encoding="utf-8")
        self.conn.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?", (iso(now_utc()), pid)
        )
        self.conn.commit()

    def compose_bible_context(self, pid: str, doc_names: list[str], max_chars: int = 4000) -> str:
        """Controlled context selection: only chosen docs, hard char cap.
        Never sends the whole bible automatically."""
        parts: list[str] = []
        total = 0
        for name in doc_names:
            if name not in BIBLE_DOCS:
                raise ProjectError(f"Unknown bible document {name}")
            try:
                body = self.read_bible_doc(pid, name)
            except ProjectError:
                continue
            room = max_chars - total
            if room <= 200:
                break
            parts.append(f"### {name}\n{body[:room]}")
            total += min(len(body), room)
        if not parts:
            return ""
        return "\n\n".join(parts)[:max_chars]

    # --- scenes ---------------------------------------------------------------
    def create_scene(self, pid: str, title: str, summary: str = "") -> dict:
        self.get_project(pid)
        slug = slugify(title)
        row = self.conn.execute(
            "SELECT 1 FROM scenes WHERE project_id = ? AND slug = ?", (pid, slug)
        ).fetchone()
        if row is not None:
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"
        sid = new_id("scn")
        now = iso(now_utc())
        self.conn.execute(
            "INSERT INTO scenes (id, project_id, slug, title, summary, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 'planned', ?, ?)",
            (sid, pid, slug, title.strip(), summary.strip(), now, now),
        )
        self.conn.commit()
        project = self.get_project(pid)
        sdir = safe_join(self.root, project["slug"], "scenes", sid)
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "scene.md").write_text(
            f"# {title}\n\n{summary}\n\n## Shot list\n\n- [TO FILL]\n", encoding="utf-8"
        )
        return self.get_scene(sid)

    def get_scene(self, sid: str) -> dict:
        row = self.conn.execute("SELECT * FROM scenes WHERE id = ?", (sid,)).fetchone()
        if row is None:
            raise ProjectError(f"Scene {sid} not found")
        return dict(row)

    def list_scenes(self, pid: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY created_at", (pid,)
        ).fetchall()
        return [dict(r) for r in rows]
