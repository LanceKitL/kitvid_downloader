import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app import config
from app.jobs import Job, JobManager


def make_job(job_id: str = "abc123", output_dir: str = "/tmp/kitvid") -> Job:
    return Job(
        id=job_id,
        url="https://example.com/video",
        format_id="137",
        audio_only=False,
        needs_audio=True,
        output_dir=output_dir,
    )


class ProgressParsingTests(unittest.TestCase):
    def test_parses_bytes_and_percent(self):
        job = make_job()
        JobManager._handle_line(
            job, "PROGRESS:downloading:1048576:4194304:NA:2048:12"
        )

        self.assertEqual(job.downloaded_bytes, 1048576)
        self.assertEqual(job.total_bytes, 4194304)
        self.assertFalse(job.total_bytes_is_estimate)
        self.assertAlmostEqual(job.progress, 25.0)
        self.assertEqual(job.eta, 12)
        self.assertEqual(job.stage, "Downloading")

    def test_uses_estimate_when_total_is_missing(self):
        job = make_job()
        JobManager._handle_line(
            job, "PROGRESS:downloading:1048576:NA:4194304:NA:NA"
        )

        self.assertEqual(job.total_bytes, 4194304)
        self.assertTrue(job.total_bytes_is_estimate)

    def test_finished_progress_reaches_100(self):
        job = make_job()
        JobManager._handle_line(job, "PROGRESS:finished:4194304:4194304:NA:NA:NA")

        self.assertEqual(job.progress, 100.0)
        self.assertEqual(job.stage, "Finishing")


class JobSerializationTests(unittest.TestCase):
    def test_to_dict_includes_output_and_byte_fields(self):
        job = make_job()
        job.downloaded_bytes = 1024
        job.total_bytes = 4096
        job.total_bytes_is_estimate = True

        data = job.to_dict()

        self.assertEqual(data["output_dir"], "/tmp/kitvid")
        self.assertEqual(data["downloaded_bytes"], 1024)
        self.assertEqual(data["total_bytes"], 4096)
        self.assertTrue(data["total_bytes_is_estimate"])

    def test_to_dict_includes_live_flag(self):
        job = make_job()
        job.is_live = True

        self.assertTrue(job.to_dict()["is_live"])


class LiveDownloadTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_download_is_not_limited_by_job_timeout(self):
        class DelayedStream:
            async def __aiter__(self):
                await asyncio.sleep(0.02)
                yield b"PROGRESS:downloading:1:NA:NA:NA:NA\n"

        class EmptyStream:
            async def __aiter__(self):
                if False:
                    yield b""

        with tempfile.TemporaryDirectory() as temp_dir:
            job = make_job(output_dir=temp_dir)
            job.is_live = True
            output_dir = Path(temp_dir) / job.id
            output_dir.mkdir()
            (output_dir / "live.mp4").write_bytes(b"video")

            process = type(
                "Process",
                (),
                {
                    "stdout": DelayedStream(),
                    "stderr": EmptyStream(),
                    "returncode": 0,
                    "wait": AsyncMock(return_value=0),
                },
            )()
            manager = JobManager()

            with (
                patch.object(config, "DOWNLOAD_TIMEOUT_SECONDS", 0.001),
                patch("app.jobs.build_download_args", return_value=["yt-dlp"]),
                patch(
                    "app.jobs.asyncio.create_subprocess_exec",
                    new=AsyncMock(return_value=process),
                ),
            ):
                await manager._run(job)

            self.assertEqual(job.status, "finished")
            self.assertEqual(job.filename, "live.mp4")


class JobListingTests(unittest.TestCase):
    def test_lists_newest_first(self):
        manager = JobManager()
        older = make_job("older")
        newer = make_job("newer")
        older.created_at = 100
        newer.created_at = 200
        manager.jobs = {"older": older, "newer": newer}

        self.assertEqual([job.id for job in manager.list_jobs()], ["newer", "older"])


if __name__ == "__main__":
    unittest.main()
