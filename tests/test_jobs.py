import unittest

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
