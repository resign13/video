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

    def frame(self):
        image = io.BytesIO()
        Image.new("RGB", (640, 480), "white").save(image, "PNG")
        image.seek(0)
        return (image, "frame.png")

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
                               reference_videos=(io.BytesIO(b"test video"), "video.mp4"),
                               reference_audios=(io.BytesIO(b"test audio"), "audio.mp3"),
                               first_image=self.frame(), last_image=self.frame())
        self.assertEqual(response.status_code, 202, response.json)
        self.assertNotIn("api_key", response.json)
        rerun = self.client.post(f"/api/tasks/{response.json['id']}/rerun")
        self.assertEqual(rerun.status_code, 202, rerun.json)
        self.assertNotIn("media_paths", response.json)
        original = self.module.TASKS[response.json["id"]]
        copied = self.module.TASKS[rerun.json["id"]]
        persisted = self.module.TASK_REPOSITORY.load_all()[response.json["id"]]
        self.assertEqual(persisted["media_paths"], original["media_paths"])
        for field in self.module.REFERENCE_MEDIA_FIELDS:
            source_path = Path(original["media_paths"][field][0])
            copied_path = Path(copied["media_paths"][field][0])
            self.assertNotEqual(source_path, copied_path)
            self.assertEqual(source_path.read_bytes(), copied_path.read_bytes())
            resource = self.client.get(response.json["media_files"][field][0]["url"])
            self.assertEqual(resource.status_code, 200)
            self.assertEqual(resource.data, source_path.read_bytes())
            resource.close()
        media_url = response.json["media_files"]["reference_videos"][0]["url"]
        resource = self.client.get(media_url, headers={"Range": "bytes=0-3"})
        self.assertEqual(resource.status_code, 206)
        self.assertEqual(resource.data, b"test")
        resource.close()
        self.assertEqual(self.client.get(media_url.replace("reference_videos", "invalid")).status_code, 404)
        self.assertEqual(self.client.get(media_url.replace("video.mp4", "other.mp4")).status_code, 404)

    def test_invalid_inputs_are_rejected_before_worker(self):
        cases = [
            (self.module.KYY_C5_MODEL, {"seconds": "4"}),
            (self.module.KYY_C5_MODEL, {"resolution": "480p"}),
            (self.module.KYY_C5_MODEL, {"first_image": self.frame()}),
            (self.module.KYY_C3_MODEL, {"aspect_ratio": "2:3"}),
            (self.module.KYY_C3_MODEL, {"seconds": "31"}),
            (self.module.KYY_C3_MODEL, {"reference_videos": [(io.BytesIO(b"video"), f"{i}.mp4") for i in range(11)]}),
            (self.module.KYY_C3_MODEL, {"reference_audios": (io.BytesIO(b"wrong"), "wrong.exe")}),
            (self.module.KYY_C3_MODEL, {"reference_audios": "https://example.com/a.mp3"}),
            (self.module.KYY_C3_MODEL, {"first_image": (io.BytesIO(b"not an image"), "invalid.png")}),
            (self.module.KYY_C3_MODEL, {"reference_videos": (io.BytesIO(b""), "empty.mp4")}),
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
                frames = {"first_image": self.frame(), "last_image": self.frame()} if model == self.module.KYY_C3_MODEL else {}
                response = self.create(model, aspect_ratio="2:3" if model == self.module.KYY_C5_MODEL else "1:1",
                                       images=(image, "reference.jpg"), reference_videos=(io.BytesIO(b"video"), "v.mp4"), **frames)
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
                    self.assertEqual(payload["reference_videos"], self.module.build_task_media_urls(task, "reference_videos"))
                    self.assertTrue(payload["reference_videos"][0].startswith(self.module.PUBLIC_WEB_BASE_URL.rstrip('/') + "/api/tasks/"))
                    self.assertNotIn("generate_audio", payload)
                    self.assertEqual(payload.get("n"), "1" if model == self.module.KYY_C5_MODEL else None)
                    for field in frames:
                        self.assertEqual(payload[field], self.module.build_task_media_urls(task, field)[0])
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

    def test_upload_size_limits(self):
        with patch.dict(self.module.REFERENCE_MEDIA_FIELDS["reference_videos"], {"max_bytes": 3}):
            response = self.create(self.module.KYY_C3_MODEL, reference_videos=(io.BytesIO(b"oversized"), "big.mp4"))
            self.assertEqual(response.status_code, 400)
        with patch.dict(self.module.app.config, {"MAX_CONTENT_LENGTH": 100}):
            response = self.create(self.module.KYY_C3_MODEL, reference_videos=(io.BytesIO(b"video"), "v.mp4"))
            self.assertEqual(response.status_code, 413)
            self.assertIsNotNone(response.json["error"])
        self.worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
