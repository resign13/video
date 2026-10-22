"""MEAICC D-series API validation and wire format, without paid requests."""
import importlib.util
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image


class MeaiccDModelsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        backend = Path(__file__).resolve().parents[1]
        isolated = Path(cls.directory.name) / "app.py"
        shutil.copyfile(backend / "app.py", isolated)
        sys.path.insert(0, str(backend))
        spec = importlib.util.spec_from_file_location("meaicc_d_test_app", isolated)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):
        sys.path.pop(0)
        cls.directory.cleanup()

    def setUp(self):
        self.client = self.module.app.test_client()
        patch.object(self.module, "start_task_worker").start()
        patch.object(self.module, "MEAICC_API_KEY", "test-shared-meaicc-key").start()
        self.addCleanup(patch.stopall)

    def create(self, model, **kwargs):
        return self.client.post("/api/tasks", data={"model_family": model, "prompt": "Product video",
            "seconds": "5", "resolution": "480p" if model == "sd-2.5-d2" else "720p",
            "aspect_ratio": "16:9", **kwargs})

    @staticmethod
    def frame():
        buffer = io.BytesIO()
        Image.new("RGB", (640, 480), "white").save(buffer, "PNG")
        buffer.seek(0)
        return (buffer, "frame.png")

    def test_model_capabilities_and_shared_key(self):
        models = {item["value"]: item for item in self.client.get("/api/models").json["models"]}
        for family in self.module.MEAICC_D_MODELS:
            with self.subTest(model=family):
                model = models[family]
                self.assertEqual(model["seconds_options"], [str(i) for i in range(5, 31)])
                self.assertEqual(model["resolutions"], ["480p" if family == "sd-2.5-d2" else "720p"])
                self.assertEqual((model["min_images"], model["max_images"]), (0, 30))
                self.assertEqual(model["media_upload_limits"]["reference_videos"]["limit"], 0 if family == "sd-2.5-d1" else 10)
                self.assertEqual(self.module.get_backend_config(family)["api_key"], "test-shared-meaicc-key")

    def test_text_media_payload_and_rerun(self):
        for family in self.module.MEAICC_D_MODELS:
            with self.subTest(model=family):
                files = {"reference_audios": (io.BytesIO(b"audio"), "a.mp3"), "first_image": self.frame()}
                if family != "sd-2.5-d1":
                    files["reference_videos"] = (io.BytesIO(b"video"), "v.mp4")
                response = self.create(family, seconds="30", **files)
                self.assertEqual(response.status_code, 202)
                task = self.module.TASKS[response.json["id"]]
                upstream = Mock(status_code=200, headers={})
                upstream.json.return_value = {"id": "remote-test"}
                with patch.object(self.module.RUNNER, "request_with_retry", return_value=upstream) as call:
                    self.assertEqual(self.module.RUNNER.submit_task(task), "remote-test")
                args, kwargs = call.call_args
                self.assertEqual(args[:2], ("post", f"{self.module.MEAICC_BASE_URL}/v1/videos"))
                self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-shared-meaicc-key")
                payload = kwargs["json"]
                self.assertEqual(payload["model"], family)
                self.assertEqual(payload["parameters"]["resolution"], "480p" if family == "sd-2.5-d2" else "720p")
                self.assertEqual(payload["parameters"]["duration"], 30)
                types = {item["type"] for item in payload["input"]["media"]}
                self.assertIn("reference_voice", types)
                self.assertIn("first_frame", types)
                self.assertEqual("reference_video" in types, family != "sd-2.5-d1")
                rerun = self.client.post(f"/api/tasks/{task['id']}/rerun")
                self.assertEqual(rerun.status_code, 202)
                self.assertEqual(self.module.TASKS[rerun.json["id"]]["seconds"], "30")

    def test_invalid_parameters_are_rejected_before_generation(self):
        for family, changes in (("sd-2.5-d1", {"seconds": "31"}), ("sd-2.5-d1", {"prompt": "x" * 15001}),
                                ("sd-2.5-d1", {"reference_videos": (io.BytesIO(b"video"), "v.mp4")}),
                                ("sd-2.5-d2", {"resolution": "720p"}), ("sd-2.5-d3", {"aspect_ratio": "2:3"}),
                                ("sd-2.5-d3", {"reference_audios": [(io.BytesIO(b"audio"), f"{i}.mp3") for i in range(11)]})):
            with self.subTest(model=family, fields=list(changes)):
                self.assertEqual(self.create(family, **changes).status_code, 400)
        self.module.start_task_worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
