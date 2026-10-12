"""Exercise the KYY integration without sending paid generation requests."""
import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image


class KyyModelsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        backend = Path(__file__).resolve().parents[1]
        isolated_app = Path(cls.directory.name) / "app.py"
        shutil.copyfile(backend / "app.py", isolated_app)
        sys.path.insert(0, str(backend))
        spec = importlib.util.spec_from_file_location("kyy_test_app", isolated_app)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):
        sys.path.pop(0)
        cls.directory.cleanup()

    def setUp(self):
        self.client = self.module.app.test_client()
        self.worker = patch.object(self.module, "start_task_worker").start()
        self.addCleanup(patch.stopall)

    def create(self, model, **kwargs):
        return self.client.post("/api/tasks", data={
            "model_family": model, "prompt": "Product video", "seconds": "5",
            "resolution": "720p", "aspect_ratio": "16:9", **kwargs,
        })

    def test_capabilities_and_key_reuse(self):
        models = {m["value"]: m for m in self.client.get("/api/models").json["models"]}
        c5 = models[self.module.KYY_C5_MODEL]
        c3 = models[self.module.KYY_C3_MODEL]
        self.assertEqual(c5["seconds_options"], [str(i) for i in range(5, 31)])
        self.assertEqual(c3["seconds_options"], [str(i) for i in range(4, 31)])
        self.assertEqual(c5["resolutions"], ["720p"])
        self.assertEqual(c3["resolutions"], ["720p", "480p"])
        self.assertIn("2:3", c5["aspect_ratios"])
        self.assertEqual(c3["aspect_ratios"], ["16:9", "9:16", "1:1"])
        for model in (c5, c3):
            self.assertEqual((model["min_images"], model["max_images"]), (0, 30))
            config = self.module.get_backend_config(model["value"])
            self.assertEqual(config["api_key"], self.module.LUXVID_API_KEY)
            self.assertEqual(config["api_base"], self.module.LUXVID_BASE_URL)

    def test_text_only_submission_and_rerun_preserve_media(self):
        response = self.create(self.module.KYY_C3_MODEL, seconds="4", resolution="480p",
                               reference_videos="https://example.com/video.mp4",
                               reference_audios="https://example.com/audio.mp3",
                               first_image="https://example.com/first.jpg",
                               last_image="https://example.com/last.jpg")
        self.assertEqual(response.status_code, 202, response.json)
        self.assertNotIn("api_key", response.json)
        rerun = self.client.post(f"/api/tasks/{response.json['id']}/rerun")
        self.assertEqual(rerun.status_code, 202, rerun.json)
        for field in ("reference_videos", "reference_audios", "first_image", "last_image"):
            self.assertEqual(rerun.json[field], response.json[field])

    def test_invalid_inputs_are_rejected_before_worker(self):
        cases = [
            (self.module.KYY_C5_MODEL, {"seconds": "4"}),
            (self.module.KYY_C5_MODEL, {"resolution": "480p"}),
            (self.module.KYY_C5_MODEL, {"first_image": "https://example.com/first.jpg"}),
            (self.module.KYY_C3_MODEL, {"aspect_ratio": "2:3"}),
            (self.module.KYY_C3_MODEL, {"seconds": "31"}),
            (self.module.KYY_C3_MODEL, {"reference_videos": "\n".join(["https://example.com/v.mp4"] * 11)}),
            (self.module.KYY_C3_MODEL, {"reference_audios": "file:///audio.mp3"}),
        ]
        for model, fields in cases:
            with self.subTest(model=model, fields=fields):
                self.assertEqual(self.create(model, **fields).status_code, 400)
        self.worker.assert_not_called()
        self.assertEqual(self.create("seedance2.5c1").status_code, 400)

    def test_image_payload_and_result_polling(self):
        for model in (self.module.KYY_C5_MODEL, self.module.KYY_C3_MODEL):
            with self.subTest(model=model):
                image = io.BytesIO()
                Image.new("RGB", (640, 480), "white").save(image, "JPEG")
                image.seek(0)
                frames = {"first_image": "https://example.com/first.jpg", "last_image": "https://example.com/last.jpg"} if model == self.module.KYY_C3_MODEL else {}
                response = self.create(model, aspect_ratio="2:3" if model == self.module.KYY_C5_MODEL else "1:1",
                                       images=(image, "reference.jpg"), reference_videos="https://example.com/v.mp4", **frames)
                self.assertEqual(response.status_code, 202, response.json)
                task = self.module.TASKS[response.json["id"]]
                submit_response = Mock(status_code=200)
                submit_response.json.return_value = {"data": {"id": "mcp_test", "status": "queued"}}
                with patch.object(self.module, "upload_image_to_imgbb", return_value="https://example.com/image.jpg"), \
                        patch.object(self.module.RUNNER, "request_with_retry", return_value=submit_response) as request:
                    self.assertEqual(self.module.RUNNER.submit_task(task), "mcp_test")
                    payload = request.call_args.kwargs["json"]
                    self.assertEqual(request.call_args.args[1], self.module.LUXVID_BASE_URL + "/v2/model-center/tasks")
                    self.assertEqual(payload["model"], model)
                    self.assertEqual(payload["reference_images"], ["https://example.com/image.jpg"])
                    self.assertEqual(payload["reference_videos"], ["https://example.com/v.mp4"])
                    self.assertNotIn("generate_audio", payload)
                    self.assertEqual(payload.get("n"), "1" if model == self.module.KYY_C5_MODEL else None)
                    for field, value in frames.items():
                        self.assertEqual(payload[field], value)
                for field in ("result_url", "video_url", "media_url"):
                    poll_response = Mock(status_code=200)
                    poll_response.json.return_value = {"data": {"status": "completed", "object": "video", field: "https://example.com/result.mp4"}}
                    with patch.object(self.module.RUNNER, "request_with_retry", return_value=poll_response) as request:
                        self.assertEqual(self.module.RUNNER.poll_task(task, "mcp_test"), "https://example.com/result.mp4")
                        self.assertTrue(request.call_args.args[1].endswith("/v2/model-center/tasks/mcp_test"))
                poll_response.json.return_value = {"status": "failed", "error": None, "error_message": "Provider rejected input"}
                with patch.object(self.module.RUNNER, "request_with_retry", return_value=poll_response):
                    with self.assertRaisesRegex(RuntimeError, "Provider rejected input"):
                        self.module.RUNNER.poll_task(task, "mcp_test")


if __name__ == "__main__":
    unittest.main()
