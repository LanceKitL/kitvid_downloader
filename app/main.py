import asyncio
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, folder_picker, settings
from .jobs import manager
from .ytdlp import YtdlpError, fetch_info, validate_format_id, validate_url

STATIC_DIR = Path(__file__).resolve().parent / "static"
_browse_active = False


class InfoRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class JobRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    format_id: str | None = Field(default=None, max_length=64)
    audio_only: bool = False
    needs_audio: bool = False
    title: str | None = Field(default=None, max_length=300)


class SettingsRequest(BaseModel):
    download_dir: str = Field(min_length=1, max_length=4096)


class BrowseRequest(BaseModel):
    initial_dir: str | None = Field(default=None, max_length=4096)


class SpeedRequest(BaseModel):
    profile: str = Field(min_length=1, max_length=32)


async def _cleanup_loop() -> None:
    while True:
        try:
            await asyncio.sleep(300)
            manager.cleanup_expired()
        except asyncio.CancelledError:
            raise
        except Exception:
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.load()
    settings.ensure_download_dir()
    cleanup_task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        for job_id in list(manager.jobs):
            if manager.jobs[job_id].status not in ("finished", "error", "cancelled"):
                await manager.cancel(job_id)
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=config.APP_NAME,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def enforce_same_origin(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin:
            origin_host = urlsplit(origin).netloc
            request_host = request.headers.get("host", "")
            if origin_host != request_host:
                return JSONResponse(
                    {"detail": "Cross-origin requests are not allowed."}, status_code=403
                )
    return await call_next(request)


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "app": config.APP_NAME, "yt_dlp": config.YTDLP_BIN}


@app.get("/api/settings")
async def get_settings() -> dict:
    return settings.current()


@app.put("/api/settings")
async def update_settings(payload: SettingsRequest) -> dict:
    try:
        return settings.save_download_dir(payload.download_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/settings/speed")
async def update_speed(payload: SpeedRequest) -> dict:
    try:
        return settings.save_speed_profile(payload.profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/browse")
async def browse_settings(payload: BrowseRequest) -> dict:
    global _browse_active
    if _browse_active:
        raise HTTPException(status_code=409, detail="A folder picker is already open.")

    _browse_active = True
    try:
        path = await asyncio.to_thread(folder_picker.pick_folder, payload.initial_dir)
    except folder_picker.FolderPickerUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    finally:
        _browse_active = False

    if not path:
        return {"cancelled": True, "download_dir": None}
    return {"cancelled": False, "download_dir": path}


@app.post("/api/info")
async def info(payload: InfoRequest) -> dict:
    try:
        url = validate_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return await asyncio.to_thread(fetch_info, url)
    except YtdlpError as exc:
        raise HTTPException(
            status_code=422, detail={"message": exc.message, "detail": exc.detail}
        ) from exc


@app.post("/api/jobs")
async def create_job(payload: JobRequest) -> dict:
    try:
        url = validate_url(payload.url)
        format_id = validate_format_id(payload.format_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = manager.create(
        url=url,
        format_id=format_id,
        audio_only=payload.audio_only,
        needs_audio=payload.needs_audio,
        title=payload.title,
    )
    return job.to_dict()


@app.get("/api/jobs")
async def list_jobs() -> dict:
    jobs = manager.list_jobs()
    active = sum(1 for job in jobs if job.status in ("queued", "running"))
    return {"jobs": [job.to_dict() for job in jobs], "active": active}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.to_dict()


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    await manager.cancel(job_id)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/file")
async def get_file(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != "finished" or not job.file_path:
        raise HTTPException(status_code=409, detail="File is not ready yet.")

    path = Path(job.file_path).resolve()
    try:
        path.relative_to(Path(job.output_dir).resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid file path.") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File has expired or was deleted.")

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=job.filename or path.name)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
