import asyncio
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .ytdlp import build_download_args, friendly_error

TERMINAL_STATES = {"finished", "error", "cancelled"}


@dataclass
class Job:
    id: str
    url: str
    format_id: str | None
    audio_only: bool
    needs_audio: bool
    output_dir: str
    title: str | None = None

    status: str = "queued"
    stage: str = "Queued"
    progress: float = 0.0
    speed: float | None = None
    eta: int | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    total_bytes_is_estimate: bool = False
    error: str | None = None
    error_detail: str | None = None

    filename: str | None = None
    file_path: str | None = None
    file_size: int | None = None

    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    process: asyncio.subprocess.Process | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        download_url = (
            f"/api/jobs/{self.id}/file" if self.status == "finished" and self.file_path else None
        )
        return {
            "id": self.id,
            "url": self.url,
            "format_id": self.format_id,
            "audio_only": self.audio_only,
            "title": self.title,
            "output_dir": self.output_dir,
            "status": self.status,
            "stage": self.stage,
            "progress": round(self.progress, 1),
            "speed": self.speed,
            "eta": self.eta,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "total_bytes_is_estimate": self.total_bytes_is_estimate,
            "error": self.error,
            "error_detail": self.error_detail,
            "filename": self.filename,
            "file_size": self.file_size,
            "download_url": download_url,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


def _parse_number(value: str) -> float | None:
    if value in ("", "NA", "None", "none"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self._semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_DOWNLOADS)
        self._tasks: set[asyncio.Task] = set()

    def create(
        self,
        url: str,
        format_id: str | None,
        audio_only: bool,
        needs_audio: bool,
        title: str | None,
        output_dir: Path | None = None,
    ) -> Job:
        job_id = uuid.uuid4().hex[:12]
        target = Path(output_dir or config.DOWNLOAD_DIR).expanduser().resolve()
        job = Job(
            id=job_id,
            url=url,
            format_id=format_id,
            audio_only=audio_only,
            needs_audio=needs_audio,
            output_dir=str(target),
            title=title,
        )
        self.jobs[job_id] = job

        task = asyncio.create_task(self._run(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        return sorted(self.jobs.values(), key=lambda job: job.created_at, reverse=True)

    async def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        if job.status in TERMINAL_STATES:
            self.delete(job_id)
            return True

        job.status = "cancelled"
        job.stage = "Cancelled"
        job.finished_at = time.time()
        process = job.process
        if process and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
        self._remove_dir(job)
        return True

    def delete(self, job_id: str) -> bool:
        if job_id not in self.jobs:
            return False
        job = self.jobs.pop(job_id)
        process = job.process
        if process and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        self._remove_dir(job)
        return True

    def cleanup_expired(self) -> int:
        if config.FILE_TTL_MINUTES <= 0:
            return 0
        cutoff = time.time() - config.FILE_TTL_MINUTES * 60
        expired = [
            job_id
            for job_id, job in self.jobs.items()
            if job.finished_at is not None
            and job.finished_at < cutoff
            and job.status in TERMINAL_STATES
        ]
        for job_id in expired:
            self.delete(job_id)
        return len(expired)

    @staticmethod
    def _remove_dir(job: Job) -> None:
        out_dir = Path(job.output_dir) / job.id
        shutil.rmtree(out_dir, ignore_errors=True)

    async def _run(self, job: Job) -> None:
        out_dir = Path(job.output_dir) / job.id

        async with self._semaphore:
            if job.status == "cancelled":
                return

            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._fail(job, "Could not create the download directory.", str(exc))
                return

            args = build_download_args(
                job.url,
                out_dir,
                format_id=job.format_id,
                audio_only=job.audio_only,
                needs_audio=job.needs_audio,
            )

            job.status = "running"
            job.stage = "Starting yt-dlp"

            try:
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError:
                self._fail(job, "yt-dlp is not installed or not on PATH.")
                self._remove_dir(job)
                return
            except OSError as exc:
                self._fail(job, "Could not start yt-dlp.", str(exc))
                self._remove_dir(job)
                return

            job.process = process
            stderr_chunks: list[str] = []

            async def drain_stderr() -> None:
                assert process.stderr is not None
                async for raw in process.stderr:
                    text = raw.decode(errors="replace")
                    if text:
                        stderr_chunks.append(text)

            stderr_task = asyncio.create_task(drain_stderr())

            try:
                async with asyncio.timeout(config.DOWNLOAD_TIMEOUT_SECONDS):
                    assert process.stdout is not None
                    async for raw in process.stdout:
                        self._handle_line(job, raw.decode(errors="replace").rstrip())
                    returncode = await process.wait()
                    await asyncio.gather(stderr_task, return_exceptions=True)
            except TimeoutError:
                job.status = "cancelled"
                job.stage = "Timed out"
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
                stderr_task.cancel()
                await asyncio.gather(stderr_task, return_exceptions=True)
                self._fail(job, "The download timed out.")
                self._remove_dir(job)
                return
            except asyncio.CancelledError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                stderr_task.cancel()
                await asyncio.gather(stderr_task, return_exceptions=True)
                raise

            if job.status == "cancelled":
                self._remove_dir(job)
                return

            if returncode != 0:
                detail = "".join(stderr_chunks).strip()[-2000:]
                self._fail(job, friendly_error(detail), detail)
                self._remove_dir(job)
                return

            file_path = self._find_output(out_dir)
            if not file_path:
                self._fail(job, "yt-dlp finished but produced no file.")
                self._remove_dir(job)
                return

            job.file_path = str(file_path)
            job.filename = file_path.name
            try:
                job.file_size = file_path.stat().st_size
            except OSError:
                job.file_size = None
            job.status = "finished"
            job.stage = "Done"
            job.progress = 100.0
            job.speed = None
            job.eta = None
            job.finished_at = time.time()

    @staticmethod
    def _handle_line(job: Job, line: str) -> None:
        if line.startswith("PROGRESS:"):
            parts = line.split(":", 6)
            if len(parts) != 7:
                return
            _, status, downloaded, total, estimate, speed, eta = parts
            job.status = "running"
            downloaded_bytes = _parse_number(downloaded)
            total_bytes = _parse_number(total)
            estimated_bytes = _parse_number(estimate)
            effective_total = total_bytes or estimated_bytes

            if status == "finished":
                job.progress = 100.0
                job.stage = "Finishing"
            elif downloaded_bytes is not None and effective_total:
                job.progress = min(99.0, downloaded_bytes / effective_total * 100)
                job.stage = "Downloading"
            elif downloaded_bytes is not None and downloaded_bytes > 0:
                job.stage = "Downloading"

            job.downloaded_bytes = (
                int(downloaded_bytes) if downloaded_bytes is not None else None
            )
            job.total_bytes = int(effective_total) if effective_total else None
            job.total_bytes_is_estimate = (
                total_bytes is None and estimated_bytes is not None
            )
            job.speed = _parse_number(speed)
            eta_value = _parse_number(eta)
            job.eta = int(eta_value) if eta_value is not None else None
            return

        if line.startswith("[Merger]") or "Merging formats" in line:
            job.stage = "Merging audio and video"
            job.progress = max(job.progress, 99.0)
        elif line.startswith("[ExtractAudio]"):
            job.stage = "Extracting audio"
            job.progress = max(job.progress, 99.0)
        elif line.startswith("[download] Destination"):
            job.stage = "Downloading"
        elif line.startswith("[ffmpeg]") or line.startswith("[Fixup"):
            job.stage = "Processing with FFmpeg"
            job.progress = max(job.progress, 99.0)

    @staticmethod
    def _find_output(out_dir: Path) -> Path | None:
        candidates = []
        for path in out_dir.iterdir():
            if not path.is_file():
                continue
            if path.name.endswith((".part", ".ytdl", ".temp")):
                continue
            try:
                if path.stat().st_size > 0:
                    candidates.append(path)
            except OSError:
                continue
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_size)

    @staticmethod
    def _fail(job: Job, message: str, detail: str | None = None) -> None:
        job.status = "error"
        job.stage = "Failed"
        job.error = message
        job.error_detail = detail
        job.speed = None
        job.eta = None
        job.finished_at = time.time()


manager = JobManager()
