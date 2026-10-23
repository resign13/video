"""Special 2.5 scene rules, reviewed assets, options and result fields."""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image


class Special25Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        backend = Path(__file__).resolve().parents[1]
        isolated = Path(cls.directory.name) / "app.py"
        shutil.copyfile(backend / "app.py", isolated)
        sys.path.insert(0, str(backend))
        spec = importlib.util.spec_from_file_location("special25_test_app", isolated)
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

    @staticmethod
    def image(size=(640, 480)):
        buffer = io.BytesIO()
        Image.new("RGB", size, "white").save(buffer, "PNG")
        buffer.seek(0)
        return buffer, "frame.png"

    def create(self, **changes):
        return self.client.post("/api/tasks", data={"model_family": self.module.SEEDANCE_SPECIAL_V25_MODEL,
            "prompt": "test", "seconds": "4", "aspect_ratio": "16:9", "resolution": "720p", **changes})

    def test_capabilities_and_text_only(self):
        model = next(m for m in self.client.get("/api/models").json["models"] if m["value"] == self.module.SEEDANCE_SPECIAL_V25_MODEL)
        self.assertEqual((model["min_images"], model["max_images"]), (0, 9))
        self.assertEqual(model["media_upload_limits"]["reference_videos"]["limit"], 3)
        self.assertEqual(model["media_upload_limits"]["reference_audios"]["max_bytes"], 15 * 1024 * 1024)
        self.assertTrue(model["supports_special_options"])
        self.assertTrue(model["supports_frame_images"])
        self.assertEqual(self.create().status_code, 202)

    def test_invalid_scene_and_options(self):
        invalid = [dict(last_image=self.image()), dict(images=self.image(), first_image=self.image()),
            dict(reference_audios=(io.BytesIO(b"audio"), "a.mp3")), dict(model_options='{"seed":"1.5"}'),
            dict(model_options='{"tools":{}}'), dict(model_options='{"generate_audio":"false"}'),
            dict(model_options='{"omni_reference_task_type":"extend"}'), dict(images=self.image((100, 600))),
            dict(reference_videos=[(io.BytesIO(b"v"), f"{i}.mp4") for i in range(4)])]
        for changes in invalid:
            with self.subTest(fields=list(changes)):
                self.assertEqual(self.create(**changes).status_code, 400)
        self.worker.assert_not_called()

    def test_reviewed_video_audio_and_options(self):
        options = {"seed": 42, "generate_audio": False, "return_last_frame": True,
                   "omni_reference_task_type": "extend", "tools": [{"type": "documented-tool-config"}]}
        response = self.create(aspect_ratio="adaptive", seconds="30", resolution="1080p", model_options=json.dumps(options),
            reference_videos=(io.BytesIO(b"video"), "clip.mov"), reference_audios=(io.BytesIO(b"audio"), "voice.wav"))
        self.assertEqual(response.status_code, 202)
        task = self.module.TASKS[response.json["id"]]
        calls = []

        def request(method, url, **kwargs):
            calls.append((url, kwargs.get("json")))
            if url.endswith("assetUpload"):
                return Mock(status_code=200, json=lambda: {"assetId": "asset-" + kwargs["json"]["assetType"]})
            if url.endswith("assetDetail"):
                return Mock(status_code=200, json=lambda: {"status": "ACTIVE"})
            return Mock(status_code=200, json=lambda: {"id": "remote"})

        with patch.object(self.module.RUNNER, "request_with_retry", side_effect=request):
            self.assertEqual(self.module.RUNNER.submit_task(task), "remote")
        uploads = [payload for url, payload in calls if url.endswith("assetUpload")]
        self.assertEqual([item["assetType"] for item in uploads], ["Video", "Audio"])
        self.assertTrue(all(item["model"] == "sd_2.5" for item in uploads))
        payload = calls[-1][1]
        self.assertEqual(payload["reference_videos"], ["assetId://asset-Video"])
        self.assertEqual(payload["reference_audios"], ["assetId://asset-Audio"])
        for key, value in options.items():
            self.assertEqual(payload[key], value)
        rerun = self.client.post(f"/api/tasks/{task['id']}/rerun")
        self.assertEqual(self.module.TASKS[rerun.json["id"]]["model_options"], options)
        upstream = Mock(status_code=200, json=lambda: {"data": {"status": "completed", "video_url": "https://example.com/v.mp4", "last_frame_url": "https://example.com/last.jpg"}})
        with patch.object(self.module.RUNNER, "request_with_retry", return_value=upstream):
            self.assertEqual(self.module.RUNNER.poll_task(task, "remote"), "https://example.com/v.mp4")
        self.assertEqual(task["last_frame_url"], "https://example.com/last.jpg")

    def test_frames_and_failed_asset(self):
        response = self.create(first_image=self.image(), last_image=self.image())
        self.assertEqual(response.status_code, 202)
        task = self.module.TASKS[response.json["id"]]
        with patch.object(self.module, "upload_image_to_seedance_asset", return_value="assetId://frame") as upload, \
             patch.object(self.module, "wait_for_seedance_asset_active") as active, \
             patch.object(self.module.RUNNER, "request_with_retry", return_value=Mock(status_code=200, json=lambda: {"id": "remote"})) as submit:
            self.module.RUNNER.submit_task(task)
            self.assertEqual(upload.call_count, 2)
            self.assertEqual(active.call_count, 2)
            payload = submit.call_args.kwargs["json"]
            self.assertEqual(payload["first_image"], "assetId://frame")
            self.assertEqual(payload["last_image"], "assetId://frame")
        with patch.object(self.module, "upload_image_to_seedance_asset", return_value="assetId://failed"), \
             patch.object(self.module, "wait_for_seedance_asset_active", side_effect=RuntimeError("FAILED")), \
             patch.object(self.module.RUNNER, "request_with_retry") as submit:
            with self.assertRaises(RuntimeError):
                self.module.RUNNER.submit_task(task)
            submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
