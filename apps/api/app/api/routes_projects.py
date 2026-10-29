"""Project, bible, scene, and reference routes."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.services.projects import ProjectError
from app.services.references import ReferenceError

router = APIRouter(prefix="/projects", tags=["projects"])


def _svc(request: Request):
    return request.app.state.studio


def _project_error(exc: ProjectError):
    return HTTPException(status_code=404, detail=str(exc))


@router.get("")
def list_projects(request: Request):
    return {"projects": _svc(request).projects.list_projects()}


@router.post("", status_code=201)
def create_project(request: Request, title: str = Form(...), description: str = Form("")):
    try:
        return _svc(request).projects.create_project(title, description)
    except ProjectError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{pid}")
def get_project(request: Request, pid: str):
    try:
        return _svc(request).projects.get_project(pid)
    except ProjectError as exc:
        raise _project_error(exc)


@router.patch("/{pid}")
def update_project(request: Request, pid: str, fields: dict):
    try:
        return _svc(request).projects.update_project(pid, **fields)
    except ProjectError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{pid}")
def delete_project(request: Request, pid: str, delete_files: bool = False):
    try:
        _svc(request).projects.delete_project(pid, delete_files)
        return {"deleted": pid}
    except ProjectError as exc:
        raise _project_error(exc)


# --- bible -------------------------------------------------------------------
@router.get("/{pid}/bible")
def bible_docs(request: Request, pid: str):
    try:
        return {"docs": _svc(request).projects.list_bible_docs(pid)}
    except ProjectError as exc:
        raise _project_error(exc)


@router.get("/{pid}/bible/{name}")
def read_bible_doc(request: Request, pid: str, name: str):
    try:
        return {"name": name, "content": _svc(request).projects.read_bible_doc(pid, name)}
    except ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/{pid}/bible/{name}")
def write_bible_doc(request: Request, pid: str, name: str, body: dict):
    content = body.get("content")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="body.content must be a string")
    try:
        _svc(request).projects.write_bible_doc(pid, name, content)
        return {"name": name, "saved": True}
    except ProjectError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --- scenes ------------------------------------------------------------------
@router.post("/{pid}/scenes", status_code=201)
def create_scene(request: Request, pid: str, body: dict):
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Scene title is required.")
    try:
        return _svc(request).projects.create_scene(pid, title, body.get("summary", ""))
    except ProjectError as exc:
        raise _project_error(exc)


@router.get("/{pid}/scenes")
def list_scenes(request: Request, pid: str):
    try:
        return {"scenes": _svc(request).projects.list_scenes(pid)}
    except ProjectError as exc:
        raise _project_error(exc)


# --- references ----------------------------------------------------------------
@router.post("/{pid}/references", status_code=201)
async def upload_reference(
    request: Request,
    pid: str,
    file: UploadFile = File(...),
    role: str = Form("none"),
    entity_id: str = Form(""),
):
    data = await file.read()
    mime = file.content_type or ""
    try:
        return _svc(request).references.upload(pid, file.filename or "upload", mime, data, role, entity_id)
    except ReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{pid}/references")
def list_references(request: Request, pid: str, role: str | None = None):
    return {"references": _svc(request).references.list(pid, role)}


@router.patch("/references/{asset_id}")
def set_reference_role(request: Request, asset_id: str, body: dict):
    try:
        return _svc(request).references.set_role(asset_id, body.get("role", "none"), body.get("entity_id", ""))
    except ReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/references/{asset_id}")
def delete_reference(request: Request, asset_id: str):
    try:
        _svc(request).references.delete(asset_id)
        return {"deleted": asset_id}
    except ReferenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/references/{asset_id}/file")
def reference_file(request: Request, asset_id: str):
    try:
        path = _svc(request).references.file_path(asset_id)
        return FileResponse(path)
    except ReferenceError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
