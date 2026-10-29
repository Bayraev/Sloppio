"""Reference asset uploads — validation, safe storage, metadata.

Uploads are validated by MIME allowlist, size, and real image dimensions
(Pillow decode), stored under backend-generated filenames (never user names).
"""
from __future__ import annotations

import hashlib
import io
import sqlite3
from pathlib import Path

from PIL import Image

from app.config import Settings
from app.providers.base import ProviderError
from app.services.budget import iso, now_utc
from app.services.paths import safe_join, slugify
from app.services.projects import ProjectError, ProjectService, new_id

ALLOWED_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MIN_SIDE = 300
MAX_SIDE = 6000
MIN_ASPECT = 0.4
MAX_ASPECT = 2.5
REFERENCE_ROLES = ("none", "character", "location", "prop", "style", "scene")


class ReferenceError(Exception):
    pass


class ReferenceService:
    def __init__(self, conn: sqlite3.Connection, settings: Settings, projects: ProjectService) -> None:
        self.conn = conn
        self.settings = settings
        self.projects = projects

    def _refs_dir(self, pid: str) -> Path:
        project = self.projects.get_project(pid)
        return safe_join(self.settings.resolved_projects_root(), project["slug"], "references")

    def upload(self, pid: str, filename: str, mime: str, data: bytes, role: str = "none", entity_id: str = "") -> dict:
        if role not in REFERENCE_ROLES:
            raise ReferenceError(f"Invalid role {role!r}")
        if mime not in ALLOWED_MIME:
            raise ReferenceError(f"Unsupported file type {mime}. Allowed: {', '.join(ALLOWED_MIME)}.")
        max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        if len(data) > max_bytes:
            raise ReferenceError(f"File exceeds {self.settings.max_upload_size_mb} MB limit.")
        if not data:
            raise ReferenceError("Empty file.")
        try:
            with Image.open(io.BytesIO(data)) as img:
                width, height = img.size
                fmt = (img.format or "").upper()
        except Exception as exc:
            raise ReferenceError("File is not a decodable image.") from exc
        if mime == "image/jpeg" and fmt not in ("JPEG", "JPG"):
            raise ReferenceError("File content does not match declared type.")
        if mime == "image/png" and fmt != "PNG":
            raise ReferenceError("File content does not match declared type.")
        if mime == "image/webp" and fmt != "WEBP":
            raise ReferenceError("File content does not match declared type.")
        if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
            raise ReferenceError(f"Image dimensions must be within {MIN_SIDE}-{MAX_SIDE}px per side (got {width}x{height}).")
        aspect = width / height
        if not (MIN_ASPECT <= aspect <= MAX_ASPECT):
            raise ReferenceError(f"Image aspect ratio must be within {MIN_ASPECT}-{MAX_ASPECT} (got {aspect:.2f}).")

        asset_id = new_id("ref")
        safe_name = f"{asset_id}{ALLOWED_MIME[mime]}"
        target = safe_join(self._refs_dir(pid), safe_name)
        target.write_bytes(data)
        self.conn.execute(
            "INSERT INTO assets (id, project_id, kind, role, entity_id, filename, original_filename,"
            " mime_type, size_bytes, width, height, sha256, created_at)"
            " VALUES (?, ?, 'reference', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                asset_id, pid, role, entity_id.strip(), safe_name,
                Path(filename).name[:180], mime, len(data), width, height,
                hashlib.sha256(data).hexdigest(), iso(now_utc()),
            ),
        )
        self.conn.commit()
        return self.get(asset_id)

    def get(self, asset_id: str) -> dict:
        row = self.conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise ReferenceError(f"Asset {asset_id} not found")
        return dict(row)

    def list(self, pid: str, role: str | None = None) -> list[dict]:
        if role:
            rows = self.conn.execute(
                "SELECT * FROM assets WHERE project_id = ? AND kind = 'reference' AND role = ?"
                " ORDER BY created_at DESC",
                (pid, role),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM assets WHERE project_id = ? AND kind = 'reference'"
                " ORDER BY created_at DESC",
                (pid,),
            ).fetchall()
        return [dict(r) for r in rows]

    def set_role(self, asset_id: str, role: str, entity_id: str = "") -> dict:
        if role not in REFERENCE_ROLES:
            raise ReferenceError(f"Invalid role {role!r}")
        self.conn.execute(
            "UPDATE assets SET role = ?, entity_id = ? WHERE id = ?", (role, entity_id, asset_id)
        )
        self.conn.commit()
        return self.get(asset_id)

    def file_path(self, asset_id: str) -> Path:
        asset = self.get(asset_id)
        project = self.projects.get_project(asset["project_id"])
        return safe_join(self.settings.resolved_projects_root(), project["slug"], "references", asset["filename"])

    def as_data_url(self, asset_id: str) -> str:
        import base64

        asset = self.get(asset_id)
        raw = self.file_path(asset_id).read_bytes()
        return f"data:{asset['mime_type']};base64,{base64.b64encode(raw).decode('ascii')}"

    def delete(self, asset_id: str) -> None:
        asset = self.get(asset_id)
        in_use = self.conn.execute(
            "SELECT COUNT(*) AS c FROM generation_refs WHERE asset_id = ?", (asset_id,)
        ).fetchone()["c"]
        if in_use:
            raise ReferenceError(
                "Asset is referenced by existing generations; delete is refused to preserve history."
            )
        self.conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        self.conn.commit()
        try:
            self.file_path(asset_id).unlink(missing_ok=True)
        except FileNotFoundError:
            pass

    def output_asset(self, pid: str, generation_id: str, data: bytes, provider: str) -> dict:
        """Record a generated output file under app-managed storage."""
        from app.providers.base import ProviderError as _PE

        if not data:
            raise _PE("integrity_error", "Generated video file is empty (integrity failure).")
        asset_id = new_id("out")
        ext = ".mock.mp4" if provider == "mock" else ".mp4"
        out_dir = self.settings.resolved_storage_root() / "generations"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = safe_join(out_dir, f"{asset_id}{ext}")
        path.write_bytes(data)
        self.conn.execute(
            "INSERT INTO assets (id, project_id, kind, role, entity_id, filename, original_filename,"
            " mime_type, size_bytes, width, height, sha256, created_at)"
            " VALUES (?, ?, 'output', 'none', '', ?, ?, 'video/mp4', ?, 0, 0, ?, ?)",
            (asset_id, pid, path.name, generation_id, len(data), hashlib.sha256(data).hexdigest(), iso(now_utc())),
        )
        self.conn.commit()
        return self.get(asset_id)
