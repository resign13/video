"""Persistent accounting, real fee semantics and independent calendar retention."""
from datetime import datetime
from contextlib import closing
from decimal import Decimal
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from PIL import Image

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from task_repository import TaskRepository
from usage_records import CN_TIME, expires_after_three_months, extract_provider_usage
sys.path.pop(0)


class UsageStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = TaskRepository(Path(self.temp.name) / "tasks.sqlite3")

    def task(self, identity="task-a", **kwargs):
        return {"id": identity, "created_ts": time.time(), "model_family": "sd_2.5_special_v1",
            "api_base": "https://zcbservice.aizfw.cn/kyyReactApiServer", "api_key": "sk-private-original-key-12345678",
            "request_mode": "seedance_model_center_videos_async", "seconds": "15", "duration_seconds": 120,
            "status": "queued", "usage_tracking": True, **kwargs}

    def test_atomic_records_masking_and_original_key_recovery(self):
        task = self.task()
        self.repo.save(task)
        task.update(status="completed", provider_status="completed", provider_video_seconds=14.5,
                    provider_cost_amount="0.30", provider_cost_unit="积分")
        for _ in range(3):
            self.repo.save(task)
        public = self.repo.usage.list()
        self.assertEqual(public["total"], 1)
        self.assertEqual(public["records"][0]["requested_seconds"], 15)
        self.assertEqual(public["records"][0]["actual_seconds"], 14.5)
        self.assertNotIn(task["api_key"], json.dumps(public))
        task["api_key"] = "sk-a-new-current-provider-key"
        self.repo.save(task)
        recovered = TaskRepository(self.repo.database_path).load_all()[task["id"]]
        self.assertEqual(recovered["api_key"], "sk-private-original-key-12345678")
        self.assertEqual(public["summary"]["generated_seconds"], 14.5)
        with patch.object(self.repo.usage, "save", side_effect=sqlite3.OperationalError("failed")):
            with self.assertRaises(sqlite3.OperationalError):
                self.repo.save(self.task("rollback"))
        self.assertNotIn("rollback", self.repo.load_all())

    def test_task_cleanup_does_not_remove_usage_and_exact_expiry(self):
        task = self.task()
        self.repo.save(task)
        self.repo.delete([task["id"]])
        self.assertEqual(self.repo.load_all(), {})
        self.assertEqual(self.repo.usage.list()["total"], 1)
        expiry = expires_after_three_months(task["created_ts"])
        self.repo.usage.purge(expiry - 1)
        self.assertEqual(self.repo.usage.list()["total"], 1)
        self.repo.usage.purge(expiry)
        self.assertEqual(self.repo.usage.list()["total"], 0)
        end_of_month = datetime(2026, 11, 30, 8, tzinfo=CN_TIME)
        expected = datetime(2027, 2, 28, 8, tzinfo=CN_TIME)
        self.assertEqual(expires_after_three_months(end_of_month.timestamp()), expected.timestamp())

    def test_absent_fee_zero_fee_and_separate_units(self):
        for index, cost, unit in ((1, None, None), (2, "0", "积分"), (3, "0.10", "积分"), (4, "0.20", "积分"), (5, "2.5", "CNY")):
            self.repo.save(self.task(str(index), status="completed", provider_cost_amount=cost, provider_cost_unit=unit))
        data = self.repo.usage.list()
        self.assertEqual(data["summary"]["with_cost"], 4)
        self.assertEqual(data["summary"]["without_cost"], 1)
        totals = {row["unit"]: Decimal(row["amount"]) for row in data["summary"]["cost_totals"]}
        self.assertEqual(totals, {"积分": Decimal("0.3"), "CNY": Decimal("2.5")})
        self.assertEqual(data["summary"]["generated_seconds"], 75)

    def test_filters_pagination_and_non_kyy_provider(self):
        self.repo.save(self.task("kyy"))
        self.repo.save(self.task("meaicc", api_base="https://api.meaicc.com", request_mode="meaicc_videos_async"))
        self.assertEqual(self.repo.usage.list()["total"], 1)
        all_records = self.repo.usage.list(provider="", page_size=1)
        self.assertEqual((all_records["total"], len(all_records["records"])), (2, 1))
        self.assertEqual(self.repo.usage.list(key="5678")["total"], 1)
        self.assertEqual(self.repo.usage.list(start="2000-01-01", end="2000-01-02")["total"], 0)

    def test_legacy_key_is_not_guessed(self):
        self.repo.save(self.task(usage_key_unknown=True))
        record = self.repo.usage.list()["records"][0]
        self.assertEqual(record["key_label"], "旧任务 Key 未留存")
        with closing(self.repo._connect()) as connection:
            saved = connection.execute("SELECT api_key_snapshot FROM generation_usage").fetchone()[0]
        self.assertEqual(saved, "")

    def test_provider_fields_accept_zero_and_ignore_invalid_values(self):
        mode = "seedance_model_center_videos_async"
        self.assertEqual(extract_provider_usage({"data": {"amount": 0, "actualDuration": "5.5"}}, mode),
                         {"provider_cost_amount": "0", "provider_cost_unit": "积分", "provider_video_seconds": 5.5})
        self.assertEqual(extract_provider_usage({}, mode), {})
        self.assertEqual(extract_provider_usage({"amount": False, "cost": "NaN"}, mode), {})
        self.assertEqual(extract_provider_usage({"amount": "1"}, mode, "CNY")["provider_cost_unit"], "CNY")


class UsageApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        isolated = Path(cls.directory.name) / "app.py"
        shutil.copyfile(BACKEND / "app.py", isolated)
        sys.path.insert(0, str(BACKEND))
        spec = importlib.util.spec_from_file_location("usage_test_app", isolated)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):
        sys.path.pop(0)
        cls.directory.cleanup()

    def setUp(self):
        self.module.TASKS.clear()
        with closing(self.module.TASK_REPOSITORY._connect()) as connection, connection:
            connection.execute("DELETE FROM tasks")
            connection.execute("DELETE FROM generation_usage")

    def test_poll_billing_survives_failed_download_cleanup_and_rerun(self):
        app = self.module
        client = app.app.test_client()
        with patch.object(app, "start_task_worker"), patch.object(app, "LUXVID_API_KEY", "sk-original-secret-key-987654"):
            response = client.post("/api/tasks", data={"model_family": app.KYY_C3_MODEL, "prompt": "test", "seconds": "15"})
        self.assertEqual(response.status_code, 202)
        task = app.TASKS[response.json["id"]]
        upstream = Mock(status_code=200, json=lambda: {"data": {"status": "completed", "amount": 0.32, "actualDuration": 12,
                                                               "video_url": "https://example.com/video.mp4"}})
        with patch.object(app.RUNNER, "submit_task", return_value="remote"), \
             patch.object(app.RUNNER, "request_with_retry", return_value=upstream), \
             patch.object(app.RUNNER, "download_video", side_effect=RuntimeError("download failed")):
            app.RUNNER.run_task(task["id"])
        result = client.get("/api/usage").json
        row = next(row for row in result["records"] if row["task_id"] == task["id"])
        self.assertEqual((row["cost_amount"], row["actual_seconds"], row["status"]), ("0.32", 12, "failed"))
        self.assertEqual(result["summary"]["generated_seconds"], 12)
        self.assertNotIn(task["api_key"], json.dumps(result))
        with patch.object(app, "start_task_worker"):
            rerun = client.post(f"/api/tasks/{task['id']}/rerun")
        self.assertEqual(rerun.status_code, 202)
        self.assertEqual(client.get("/api/usage").json["total"], 2)
        app.TASK_REPOSITORY.delete([task["id"]])
        self.assertEqual(client.get("/api/usage").json["total"], 2)
        for query in ("?page=-1", "?page_size=101", "?start=invalid", "?start=2027-01-01&end=2026-01-01"):
            self.assertEqual(client.get("/api/usage" + query).status_code, 400)

    def test_billing_returned_only_at_submission_is_kept(self):
        app = self.module
        client = app.app.test_client()
        with patch.object(app, "start_task_worker"):
            response = client.post("/api/tasks", data={"model_family": app.KYY_C3_MODEL, "prompt": "test", "seconds": "10"})
        task = app.TASKS[response.json["id"]]
        upstream = Mock(status_code=200, json=lambda: {"id": "remote-submitted", "amount": "0.75"})
        with patch.object(app.RUNNER, "request_with_retry", return_value=upstream):
            self.assertEqual(app.RUNNER.submit_task(task), "remote-submitted")
        app.RUNNER.update(task["id"], provider_usage={"status": "completed", "actualDuration": 10})
        row = next(row for row in client.get("/api/usage").json["records"] if row["task_id"] == task["id"])
        self.assertEqual((row["cost_amount"], row["cost_unit"]), ("0.75", "积分"))


if __name__ == "__main__":
    unittest.main()
