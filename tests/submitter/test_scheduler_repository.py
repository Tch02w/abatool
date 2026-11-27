import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from modules.submitter.scheduler_repository import SQLiteSchedulerRepository
from modules.submitter.scheduling import (
    ExecutionEvent,
    ExecutionEventKind,
    JobSpecification,
    JobState,
    ResourceRequest,
    ResourceSnapshot,
    SchedulerCore,
)


class _FailingEventRepository(SQLiteSchedulerRepository):
    def append_event(self, **_kwargs) -> None:
        raise RuntimeError("event write failed")


class SQLiteSchedulerRepositoryTests(unittest.TestCase):
    def test_reopen_keeps_history_with_mixed_case_columns_and_same_name_trigger(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheduler.db"
            with closing(SQLiteSchedulerRepository(path)) as writer:
                scheduler = SchedulerCore(writer)
                scheduler.submit(JobSpecification(job_id="original", job_name="original", work_dir=directory))
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("ALTER TABLE scheduler_jobs RENAME COLUMN state TO State")
                connection.execute(
                    "CREATE TRIGGER scheduler_meta AFTER UPDATE ON scheduler_jobs BEGIN SELECT 1; END"
                )
            with closing(SQLiteSchedulerRepository(path)) as reader:
                self.assertEqual(reader.recovery_message, "")
                self.assertEqual([job.job_id for job in reader.load_jobs()], ["original"])
                self.assertEqual(len(reader.load_events(job_id="original")), 1)
            self.assertFalse(list(path.parent.glob("*.corrupt-*")))

    def test_reopen_reads_committed_history_while_another_connection_is_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheduler.db"
            with closing(SQLiteSchedulerRepository(path)) as writer:
                scheduler = SchedulerCore(writer)
                scheduler.submit(JobSpecification(job_id="original", job_name="original", work_dir=directory))
                with writer.transaction():
                    writer.save_memory_profile("new", {"bytes": 12345})
                    with closing(SQLiteSchedulerRepository(path)) as observer:
                        self.assertEqual([row.job_id for row in observer.load_jobs()], ["original"])
                        self.assertEqual(observer.load_memory_profiles(), {})
                        self.assertEqual(len(observer.load_events(job_id="original")), 1)
                self.assertIn("new", writer.load_memory_profiles())
            self.assertFalse(list(path.parent.glob("*.corrupt-*")))

    def test_newer_version_is_refused_without_changing_the_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheduler.db"
            SQLiteSchedulerRepository(path).close()
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("ALTER TABLE scheduler_meta RENAME TO temporary_meta")
                connection.execute("ALTER TABLE temporary_meta RENAME TO Scheduler_Meta")
                connection.execute("ALTER TABLE Scheduler_Meta RENAME COLUMN key TO Key")
                connection.execute("UPDATE scheduler_meta SET value='2' WHERE key='schema_version'")
                connection.commit()
            original = hashlib.sha256(path.read_bytes()).digest()
            with self.assertRaisesRegex(ValueError, "版本.*2"), closing(SQLiteSchedulerRepository(path)):
                self.fail("Opened an unsupported database version")
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), original)
            self.assertFalse(list(path.parent.glob("*.corrupt-*")))

    def test_exclusive_database_lock_is_not_treated_as_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheduler.db"
            with closing(SQLiteSchedulerRepository(path)) as initial:
                initial.save_memory_profile("kept", {"bytes": 78})
            connect = sqlite3.connect
            with closing(connect(path)) as owner:
                owner.execute("PRAGMA journal_mode=DELETE")
                owner.execute("BEGIN EXCLUSIVE")

                def impatient_reader(*args, **kwargs):
                    kwargs["timeout"] = 0
                    return connect(*args, **kwargs)

                with patch.object(sqlite3, "connect", impatient_reader), self.assertRaises(sqlite3.OperationalError) as error:
                    SQLiteSchedulerRepository(path)
                self.assertEqual(error.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY)
            with closing(SQLiteSchedulerRepository(path)) as reader:
                self.assertIn("kept", reader.load_memory_profiles())
            self.assertFalse(list(path.parent.glob("*.corrupt-*")))

    def test_incompatible_schema_is_preserved_and_recreated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scheduler.db"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE scheduler_jobs(job_id TEXT PRIMARY KEY)")
            connection.commit()
            connection.close()

            repository = SQLiteSchedulerRepository(path)

            self.assertIn("调度状态库损坏", repository.recovery_message)
            self.assertEqual(repository.load_jobs(), [])
            repository.close()

    def test_snapshot_and_event_are_rolled_back_together(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scheduler.db"
            repository = _FailingEventRepository(path)
            scheduler = SchedulerCore(repository)

            with self.assertRaisesRegex(RuntimeError, "event write failed"):
                scheduler.submit(JobSpecification(job_id="job-1", job_name="job-1", work_dir="D:/jobs"))

            self.assertIsNone(scheduler.get("job-1"))
            repository.close()
            reopened = SQLiteSchedulerRepository(path)
            self.assertEqual(reopened.load_jobs(), [])
            reopened.close()

    def test_corrupt_database_is_preserved_and_recreated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scheduler.db"
            path.write_bytes(b"not a sqlite database")

            repository = SQLiteSchedulerRepository(path)

            self.assertIn("调度状态库损坏", repository.recovery_message)
            self.assertTrue(path.exists())
            self.assertEqual(len(list(Path(temp_dir).glob("scheduler.db.corrupt-*"))), 1)
            self.assertEqual(repository.load_jobs(), [])
            repository.close()

    def test_job_and_event_history_survive_reopen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scheduler.db"
            repository = SQLiteSchedulerRepository(path)
            scheduler = SchedulerCore(repository)
            scheduler.submit(
                JobSpecification(
                    job_id="job-1",
                    job_name="演示作业",
                    work_dir="D:/jobs/demo",
                    resources=ResourceRequest(cores=4, memory_bytes=1024),
                    dependency_job_ids=("base",),
                    metadata={"source": "测试"},
                )
            )
            scheduler.submit(
                JobSpecification(
                    job_id="base",
                    job_name="base",
                    work_dir="D:/jobs/base",
                ),
                state=JobState.COMPLETED,
            )
            allocation = scheduler.plan(ResourceSnapshot(available_slots=1)).allocations[0]
            scheduler.apply_execution_event(
                ExecutionEvent("job-1", allocation.attempt_id, ExecutionEventKind.STARTED)
            )
            scheduler.close()

            reopened_repository = SQLiteSchedulerRepository(path)
            reopened = SchedulerCore(reopened_repository)

            restored = reopened.get("job-1")
            self.assertEqual(restored.state, JobState.RUNNING)
            self.assertEqual(restored.specification.job_name, "演示作业")
            self.assertEqual(restored.specification.resources.cores, 4)
            events = reopened_repository.load_events(job_id="job-1")
            self.assertEqual(events[-1]["event_type"], "EXECUTION_STARTED")
            reopened.close()


if __name__ == "__main__":
    unittest.main()
