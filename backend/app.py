import base64
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from PIL import Image
from requests import exceptions as requests_exceptions
from werkzeug.utils import secure_filename


APP_NAME = "AI Video Studio Web"
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"


def load_dotenv_if_present():
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_value(name: str, default: str = ""):
    return os.environ.get(name, default)


load_dotenv_if_present()

BASE_URL = env_value("BASE_URL", "https://api.dealonhorizon.us")
SEEDANCE2_BASE_URL = env_value("SEEDANCE2_BASE_URL", "https://api.xbyjs.top")
HANCAT_BASE_URL = env_value("HANCAT_BASE_URL", "https://img-api.xn--1ys141f4ks.com")
GROK_IMAGINE_BASE_URL = env_value("GROK_IMAGINE_BASE_URL", "https://zexitongxue.com")
DOLO_BASE_URL = env_value("DOLO_BASE_URL", "https://zexitongxue.com")
LUXVID_BASE_URL = env_value("LUXVID_BASE_URL", "https://zcbservice.aizfw.cn/kyyReactApiServer")
SEEDANCE2_ASSET_UPLOAD_PATH = "/asset/seedance2/assetUpload"
WY_SD2_BASE_URL = env_value("WY_SD2_BASE_URL", "https://api.pro666.top")
XS_SORA_BASE_URL = env_value("XS_SORA_BASE_URL", "https://api.xs-token.com/v1")
AICLUB_BASE_URL = env_value("AICLUB_BASE_URL", "https://api.aiclub.cv")
YCY_BASE_URL = env_value("YCY_BASE_URL", "https://ycyapi.cn")
IMGBB_UPLOAD_URL = env_value("IMGBB_UPLOAD_URL", "https://api.imgbb.com/1/upload")
SORA_VIP3_BASE_URL = env_value("SORA_VIP3_BASE_URL", "https://socdabat.it.com")
SORA_VIP3_1080_BASE_URL = env_value("SORA_VIP3_1080_BASE_URL", "https://zexitongxue.com")
LONGXIA_BASE_URL = env_value("LONGXIA_BASE_URL", "https://api.longxiaai.store")
SUDASHUI_BASE_URL = env_value("SUDASHUI_BASE_URL", "https://api.sudashuiapi.com")
SUDASHUI_UPLOAD_URL = env_value("SUDASHUI_UPLOAD_URL", "https://files.sudashuiapi.com")

DEFAULT_API_KEY = env_value("DEFAULT_API_KEY")
SEEDANCE2_API_KEY = env_value("SEEDANCE2_API_KEY")
HANCAT_API_KEY = env_value("HANCAT_API_KEY")
GROK_IMAGINE_API_KEY = env_value("GROK_IMAGINE_API_KEY")
DOLO_API_KEY = env_value("DOLO_API_KEY", "sk-wWf6F6bcdk1Hs1Rd9HKfktf9Em3iJKh5NKxDp1ZEMImHOWZF")
LUXVID_API_KEY = env_value("LUXVID_API_KEY")
WY_SD2_API_KEY = env_value("WY_SD2_API_KEY", "sk-1Yo8xvcztSH4ahlMjLIZnURoZCWo40Ur7T68XZ1fB9UU0n9h")
XS_SORA_API_KEY = env_value("XS_SORA_API_KEY", "sk-xs-f462a66007a2d9597e79b627b6fb9529b6fadaf24e80933e")
AICLUB_API_KEY = env_value("AICLUB_API_KEY")
YCY_API_KEY = env_value("YCY_API_KEY", "sk-c2zWmrl9MOBfUFw8RLb0iOXClbce94ejxp851TAYytibMXiy")
VEO_STABLE_API_KEY = env_value("VEO_STABLE_API_KEY", LUXVID_API_KEY)
IMGBB_API_KEY = env_value("IMGBB_API_KEY")
SORA_VIP3_API_KEY = env_value("SORA_VIP3_API_KEY")
SORA_VIP3_1080_API_KEY = env_value("SORA_VIP3_1080_API_KEY")
LONGXIA_API_KEY = env_value("LONGXIA_API_KEY")
SUDASHUI_API_KEY = env_value("SUDASHUI_API_KEY", "sk-IHScGlbGWzhRbsBQ5d7fz3R2v0bPfvPpf4erDbMJUpViPvKF")

POLL_INTERVAL_SECONDS = 5
LONGXIA_POLL_INTERVAL_SECONDS = 120
TRANSIENT_REQUEST_RETRIES = 4
DOWNLOAD_RETRIES = 3
RETRY_SLEEP_SECONDS = 2
MAX_REFERENCES = 9
FILE_RETENTION_SECONDS = 5 * 60 * 60
CLEANUP_INTERVAL_SECONDS = 10 * 60
SECONDS_OPTIONS = ["5", "10", "15"]

PROMPT_RATIO_MODELS = {"seedance2", "jimeng-video-3.5-pro-12s", "sora-2-12s"}
LOW_RES_ONLY_MODELS = {"videos", "videos_pro", "LuxVid_video", "videos_stable_fast", "grok-imagine-video-1.5-preview"}
VEO_STABLE_MODELS = {"veo_3_1_pro_stable", "veo_3_1_fast", "veo_3_1_pro"}

MODEL_MATRIX = {
    "veo3 fast": {
        "16:9": {
            "720p": "veo_3_1_r2v_fast_landscape",
            "1080p": "veo_3_1_r2v_fast_landscape_1080p",
            "4K": "veo_3_1_r2v_fast_landscape_4k",
        },
        "9:16": {
            "720p": "veo_3_1_r2v_fast_portrait",
            "1080p": "veo_3_1_r2v_fast_portrait_1080p",
            "4K": "veo_3_1_r2v_fast_portrait_4k",
        },
    },
    "veo3": {
        "16:9": {
            "720p": "veo_3_1_i2v_s_landscape",
            "1080p": "veo_3_1_i2v_s_landscape_1080p",
            "4K": "veo_3_1_i2v_s_landscape_4k",
        },
        "9:16": {
            "720p": "veo_3_1_i2v_s_portrait",
            "1080p": "veo_3_1_i2v_s_portrait_1080p",
            "4K": "veo_3_1_i2v_s_portrait_4k",
        },
    },
    "seedance2": {
        "16:9": {"720p": "dance2-fast-15s", "1080p": "dance2-fast-15s", "4K": "dance2-fast-15s"},
        "9:16": {"720p": "dance2-fast-15s", "1080p": "dance2-fast-15s", "4K": "dance2-fast-15s"},
    },
    "jimeng-video-3.5-pro-12s": {
        "16:9": {
            "720p": "jimeng-video-3.5-pro-12s",
            "1080p": "jimeng-video-3.5-pro-12s",
            "4K": "jimeng-video-3.5-pro-12s",
        },
        "9:16": {
            "720p": "jimeng-video-3.5-pro-12s",
            "1080p": "jimeng-video-3.5-pro-12s",
            "4K": "jimeng-video-3.5-pro-12s",
        },
    },
    "sora-2-12s": {
        "16:9": {"720p": "sora-2-12s", "1080p": "sora-2-12s", "4K": "sora-2-12s"},
        "9:16": {"720p": "sora-2-12s", "1080p": "sora-2-12s", "4K": "sora-2-12s"},
    },
}

MODEL_OPTIONS = [
    {"label": "videos", "value": "videos"},
    {"label": "videos_pro", "value": "videos_pro"},
    {"label": "sd_2.0_special_720p", "value": "sd_2.0_special_720p"},
    {"label": "wy-sd2", "value": "wy-sd2"},
    {"label": "sora-v4-fast", "value": "sora-v4-fast"},
    {"label": "sora-v3-pro", "value": "sora-v3-pro"},
    {"label": "sora-2-pro", "value": "sora-2-pro"},
    {"label": "video-v1-15s", "value": "video-v1-15s"},
    {"label": "dolo", "value": "dolo"},
    {"label": "xh-sdas-fast-720p", "value": "xh-sdas-fast-720p"},
    {"label": "xh-sdas-pro-720p", "value": "xh-sdas-pro-720p"},
    {"label": "seedance2", "value": "LuxVid_video"},
    {"label": "seedance2 fast", "value": "videos_stable_fast"},
    {"label": "grok-imagine-video-1.5-preview", "value": "grok-imagine-video-1.5-preview"},
    # hidden temporarily: veo3.1-components
    # hidden temporarily: veo3.1-fast-components
    {"label": "veo_3_1_pro_stable", "value": "veo_3_1_pro_stable"},
    {"label": "veo_3_1_fast", "value": "veo_3_1_fast"},
    # hidden temporarily: veo_3_1_pro
]

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_text_from_ts(ts: float):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def short_now():
    return datetime.now().strftime("%H:%M:%S")


def resample_filter():
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return Image.LANCZOS


def process_image_to_data_url(file_path: Path):
    image = Image.open(file_path)
    max_size = 720
    if max(image.size) > max_size:
        image.thumbnail((max_size, max_size), resample_filter())
    if image.mode != "RGB":
        image = image.convert("RGB")
    quality = 72
    while True:
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        content = buffer.getvalue()
        if len(content) > 500 * 1024 and quality > 35:
            quality -= 8
            continue
        encoded = base64.b64encode(content).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"


def load_file_base64(file_path: Path):
    return base64.b64encode(file_path.read_bytes()).decode("utf-8")


def upload_image_to_imgbb(file_path: Path, api_key=IMGBB_API_KEY, timeout=120):
    response = requests.post(
        IMGBB_UPLOAD_URL,
        data={"key": api_key, "image": load_file_base64(file_path), "name": file_path.stem},
        timeout=timeout,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"ImgBB 上传失败 {response.status_code}: {response.text}")
    payload = response.json()
    data = payload.get("data") or {}
    url = data.get("url") or data.get("display_url")
    if not payload.get("success", False) or not url:
        raise RuntimeError(f"ImgBB 上传失败: {payload}")
    return url


def extract_seedance_asset_id(payload):
    """Find the asset identifier across the asset service's common response shapes."""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("asset_id", "assetId", "assetID", "id"):
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        for value in payload.values():
            asset_id = extract_seedance_asset_id(value)
            if asset_id:
                return asset_id
    elif isinstance(payload, list):
        for value in payload:
            asset_id = extract_seedance_asset_id(value)
            if asset_id:
                return asset_id
    return ""


def upload_image_to_seedance_asset(
    image_url: str,
    asset_name: str,
    api_base: str,
    headers: dict,
    request_fn,
    timeout=120,
):
    response = request_fn(
        "post",
        f"{api_base}{SEEDANCE2_ASSET_UPLOAD_PATH}",
        headers={**headers, "Content-Type": "application/json"},
        json={"assetType": "Image", "url": image_url, "name": asset_name},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    asset_id = extract_seedance_asset_id(payload)
    if not asset_id:
        raise RuntimeError(f"seedance asset upload missing asset id: {payload}")
    if asset_id.startswith(("assetId://", "asset://")):
        return asset_id
    return f"assetId://{asset_id}"


def guess_mime_type(file_path: Path):
    suffix = file_path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(suffix, "application/octet-stream")


def build_sudashui_upload_file(file_path: Path):
    allowed_image_suffixes = {".jpg", ".jpeg", ".png", ".webp"}
    suffix = file_path.suffix.lower()
    if suffix in allowed_image_suffixes:
        return file_path.name, open(file_path, "rb"), guess_mime_type(file_path), True

    image = Image.open(file_path)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    elif image.mode == "L":
        image = image.convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92, optimize=True)
    buffer.seek(0)
    filename = f"{file_path.stem or 'image'}.jpg"
    return filename, buffer, "image/jpeg", False


def upload_file_to_sudashui(file_path: Path, api_key: str, timeout=120):
    headers = {"Authorization": f"Bearer {api_key}"}
    filename, handle, mime_type, _ = build_sudashui_upload_file(file_path)
    try:
        files = {"file": (filename, handle, mime_type)}
        response = requests.post(SUDASHUI_UPLOAD_URL, headers=headers, files=files, timeout=timeout)
    finally:
        handle.close()
    if response.status_code >= 400:
        raise RuntimeError(f"sudashui upload failed {response.status_code}: {response.text}")
    payload = response.json()
    url = payload.get("url") or (payload.get("data") or {}).get("url")
    if not url:
        raise RuntimeError(f"sudashui upload missing url: {payload}")
    return url


def extract_video_url_recursive(payload):
    if isinstance(payload, str):
        return payload if payload.startswith(("http://", "https://", "/")) else ""
    if isinstance(payload, list):
        for item in payload:
            url = extract_video_url_recursive(item)
            if url:
                return url
        return ""
    if not isinstance(payload, dict):
        return ""
    for key in ("output_url", "video_url", "url", "download_url", "result_url", "file_url", "videoUrl", "downloadUrl", "resultUrl", "fileUrl"):
        url = extract_video_url_recursive(payload.get(key))
        if url:
            return url
    for value in payload.values():
        url = extract_video_url_recursive(value)
        if url:
            return url
    return ""


def normalize_video_url(url: str, api_base: str):
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"{api_base}{url}"
    return f"{api_base}/{url}"


def build_model_id(model_family: str, aspect_ratio: str, resolution: str):
    if model_family in ("videos", "videos_pro"):
        return model_family
    if model_family == "sd_2.0_special_720p":
        return model_family
    if model_family == "wy-sd2":
        return "seedance2.0-fast"
    if model_family == "sora-v4-fast":
        return "sora-v4-fast"
    if model_family == "sora-v3-pro":
        return "sora-v3-pro"
    if model_family == "sora-2-pro":
        return "sora-2-pro"
    if model_family == "video-v1-15s":
        return "video-v1-15s"
    if model_family == "dolo":
        return "dolo"
    if model_family in ("xh-sdas-fast-720p", "xh-sdas-pro-720p"):
        return model_family
    if model_family == "LuxVid_video":
        return "videos_stable"
    if model_family == "videos_stable_fast":
        return "videos_stable_fast"
    if model_family in ("veo3.1-components", "veo3.1-fast-components"):
        return "gemini-veo-3.1-generate-preview-ref-8s"
    if model_family == "grok-imagine-video-1.5-preview":
        return model_family
    if model_family in VEO_STABLE_MODELS:
        return model_family
    if model_family == "longxia-seedance-2.0":
        return "LongXia-G-Seedance-2.0"
    if model_family == "sora-vip3-pro-1080p":
        return "sora-vip3-pro-1080p"
    if model_family == "sora-vip3-pro":
        return "sora-vip3-pro-1080p" if resolution == "1080p" else "sora-vip3-pro-720p"
    return MODEL_MATRIX[model_family][aspect_ratio][resolution]


def build_size_value(aspect_ratio: str, resolution: str):
    size_map = {
        ("16:9", "480p"): "854x480",
        ("16:9", "720p"): "1280*720",
        ("16:9", "1080p"): "1920*1080",
        ("16:9", "4K"): "3840*2160",
        ("9:16", "480p"): "480x854",
        ("9:16", "720p"): "720*1280",
        ("9:16", "1080p"): "1080*1920",
        ("9:16", "4K"): "2160*3840",
        ("4:3", "480p"): "640x480",
        ("4:3", "720p"): "960*720",
        ("3:4", "480p"): "480x640",
        ("3:4", "720p"): "720*960",
        ("1:1", "480p"): "480x480",
        ("1:1", "720p"): "720*720",
        ("21:9", "480p"): "1120x480",
        ("21:9", "720p"): "1680*720",
    }
    return size_map[(aspect_ratio, resolution)]


def get_backend_config(model_family: str):
    if model_family == "sd_2.0_special_720p":
        return {
            "api_base": LUXVID_BASE_URL,
            "api_key": LUXVID_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "seedance_special_videos_async",
        }
    if model_family in ("videos", "videos_pro", "LuxVid_video", "videos_stable_fast"):
        return {
            "api_base": LUXVID_BASE_URL,
            "api_key": LUXVID_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "luxvid_videos_async",
        }
    if model_family == "wy-sd2":
        return {
            "api_base": WY_SD2_BASE_URL,
            "api_key": WY_SD2_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "wy_sd2_videos_async",
        }
    if model_family in ("sora-v4-fast", "sora-v3-pro"):
        return {
            "api_base": XS_SORA_BASE_URL,
            "api_key": XS_SORA_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "xs_sora_videos_async",
        }
    if model_family == "sora-2-pro":
        return {
            "api_base": AICLUB_BASE_URL,
            "api_key": AICLUB_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "aiclub_sora_videos_async",
        }
    if model_family == "video-v1-15s":
        return {
            "api_base": YCY_BASE_URL,
            "api_key": YCY_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "ycy_video_generations_async",
        }
    if model_family == "dolo":
        return {
            "api_base": DOLO_BASE_URL,
            "api_key": DOLO_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "dolo_videos_async",
        }
    if model_family in ("xh-sdas-fast-720p", "xh-sdas-pro-720p"):
        return {
            "api_base": SUDASHUI_BASE_URL,
            "api_key": SUDASHUI_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "sudashui_videos_async",
        }
    if model_family == "grok-imagine-video-1.5-preview":
        return {
            "api_base": GROK_IMAGINE_BASE_URL,
            "api_key": GROK_IMAGINE_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "grok_imagine_videos_async",
        }
    if model_family in ("veo3.1-components", "veo3.1-fast-components"):
        return {
            "api_base": HANCAT_BASE_URL,
            "api_key": HANCAT_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "hancat_videos_async",
        }
    if model_family in VEO_STABLE_MODELS:
        return {
            "api_base": LUXVID_BASE_URL,
            "api_key": VEO_STABLE_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "zcb_veo_videos_async",
        }
    if model_family == "sora-vip3-pro-1080p":
        return {
            "api_base": SORA_VIP3_1080_BASE_URL,
            "api_key": SORA_VIP3_1080_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "sora_vip3_multi_image",
        }
    if model_family == "longxia-seedance-2.0":
        return {
            "api_base": LONGXIA_BASE_URL,
            "api_key": LONGXIA_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "longxia_videos_async",
        }
    if model_family == "sora-vip3-pro":
        return {
            "api_base": SORA_VIP3_BASE_URL,
            "api_key": SORA_VIP3_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "sora_vip3_multi_image",
        }
    if model_family in ("seedance2", "jimeng-video-3.5-pro-12s", "sora-2-12s"):
        return {
            "api_base": SEEDANCE2_BASE_URL,
            "api_key": SEEDANCE2_API_KEY,
            "auth_mode": "bearer",
            "request_mode": "videos_async",
        }
    return {
        "api_base": BASE_URL,
        "api_key": DEFAULT_API_KEY,
        "auth_mode": "x-api-key",
        "request_mode": "generate_async",
    }


def build_request_prompt(model_family: str, prompt: str, aspect_ratio: str):
    prompt = prompt.strip()
    if model_family not in PROMPT_RATIO_MODELS:
        return prompt
    if aspect_ratio in prompt:
        return prompt
    return f"{prompt}\n{aspect_ratio}"


def get_max_images_for_model(model_family: str):
    if model_family == "sora-2-pro":
        return 1
    if model_family in ("xh-sdas-fast-720p", "xh-sdas-pro-720p"):
        return 4
    if model_family == "dolo":
        return 9
    if model_family == "video-v1-15s":
        return 0
    if model_family == "grok-imagine-video-1.5-preview":
        return 7
    if model_family in ("sora-v4-fast", "sora-v3-pro"):
        return 4
    if model_family in ("videos", "videos_pro", "sd_2.0_special_720p", "wy-sd2"):
        return 9
    if model_family in ("LuxVid_video", "videos_stable_fast"):
        return 4
    if model_family in ("veo3.1-components", "veo3.1-fast-components") or model_family in VEO_STABLE_MODELS:
        return 3
    return 9


def get_allowed_resolutions(model_family: str):
    if model_family in ("xh-sdas-fast-720p", "xh-sdas-pro-720p"):
        return ["720p"]
    if model_family == "dolo":
        return ["720p"]
    if model_family == "video-v1-15s":
        return ["1080p"]
    if model_family == "sora-v3-pro":
        return ["720p"]
    if model_family == "sora-v4-fast":
        return ["720p", "480p"]
    if model_family == "wy-sd2":
        return ["720p"]
    if model_family in ("veo3.1-components", "veo3.1-fast-components"):
        return ["1080p"]
    if model_family == "veo_3_1_pro_stable":
        return ["720p", "1080p"]
    if model_family in ("veo_3_1_fast", "veo_3_1_pro"):
        return ["720p", "1080p", "4K"]
    return ["720p"]


def get_allowed_seconds(model_family: str):
    if model_family == "sora-2-pro":
        return ["4", "8", "12"]
    if model_family in ("xh-sdas-fast-720p", "xh-sdas-pro-720p"):
        return ["10", "15"]
    if model_family == "dolo":
        return ["5", "10", "15"]
    if model_family == "video-v1-15s":
        return ["15"]
    if model_family in ("sora-v4-fast", "sora-v3-pro"):
        return [str(value) for value in range(5, 16)]
    if model_family == "videos_pro":
        return ["10", "15"]
    if model_family in ("videos", "sd_2.0_special_720p", "wy-sd2", "LuxVid_video", "videos_stable_fast"):
        return [str(value) for value in range(4, 16)]
    if model_family == "grok-imagine-video-1.5-preview":
        return ["6", "10"]
    if model_family in ("veo3.1-components", "veo3.1-fast-components") or model_family in VEO_STABLE_MODELS:
        return ["8"]
    return SECONDS_OPTIONS


def build_grok_imagine_size_value(aspect_ratio: str):
    return {
        "1:1": "1024x1024",
        "16:9": "1280x720",
        "21:9": "1792x1024",
        "9:16": "720x1280",
        "3:4": "720x1280",
        "4:3": "1280x720",
    }.get(aspect_ratio, "1280x720")


def serialize_task(task: dict):
    data = dict(task)
    data.pop("thread", None)
    data["download_url"] = f"/api/tasks/{task['id']}/download" if task.get("local_path") else None
    data["image_preview_urls"] = [
        f"/api/tasks/{task['id']}/images/{index}"
        for index, _ in enumerate(task.get("image_paths", []))
    ]
    return data


@dataclass
class WebTaskRunner:
    task_store: Dict[str, dict]
    lock: threading.Lock

    def log(self, task_id: str, message: str):
        with self.lock:
            task = self.task_store.get(task_id)
            if not task:
                return
            task["logs"].append(f"[{short_now()}] {message}")
            task["logs"] = task["logs"][-100:]

    def update(self, task_id: str, **kwargs):
        with self.lock:
            task = self.task_store.get(task_id)
            if not task:
                return
            task.update(kwargs)

    def build_headers(self, auth_mode: str, api_key: str):
        if auth_mode == "bearer":
            return {"Authorization": f"Bearer {api_key}"}
        return {"X-API-Key": api_key}

    def is_transient_request_error(self, error):
        if isinstance(error, (requests_exceptions.ConnectionError, requests_exceptions.Timeout)):
            return True
        text = str(error or "").lower()
        return any(
            marker in text
            for marker in [
                "connection aborted",
                "connection reset",
                "remote end closed connection",
                "read timed out",
                "timed out",
                "temporarily unavailable",
                "proxyerror",
                "bad gateway",
                "502",
                "503",
                "504",
                "10054",
            ]
        )

    def request_with_retry(self, method, url, **kwargs):
        last_error = None
        for attempt in range(1, TRANSIENT_REQUEST_RETRIES + 1):
            try:
                return requests.request(method, url, **kwargs)
            except requests_exceptions.RequestException as exc:
                last_error = exc
                if attempt >= TRANSIENT_REQUEST_RETRIES or not self.is_transient_request_error(exc):
                    raise
                time.sleep(RETRY_SLEEP_SECONDS)
        if last_error:
            raise last_error
        raise RuntimeError("request failed")

    def run_task(self, task_id: str):
        with self.lock:
            task = self.task_store.get(task_id)
            if not task:
                return
        started_at = time.time()
        try:
            self.update(task_id, status="running", status_text="submitting", progress=8)
            self.log(task_id, "submitting task")
            remote_task_id = self.submit_task(task)
            self.update(task_id, remote_task_id=remote_task_id, display_id=remote_task_id)
            self.log(task_id, f"remote task id: {remote_task_id}")
            remote_url = self.poll_task(task, remote_task_id)
            self.update(task_id, status_text="downloading")
            local_path = self.download_video(task, remote_url, remote_task_id)
            duration = round(time.time() - started_at, 1)
            self.update(
                task_id,
                status="completed",
                progress=100,
                status_text="completed",
                remote_url=remote_url,
                local_path=str(local_path),
                duration_seconds=duration,
                completed_ts=time.time(),
                expires_at=now_text_from_ts(time.time() + FILE_RETENTION_SECONDS),
            )
            self.log(task_id, f"completed: {local_path.name}")
        except Exception as exc:
            self.update(task_id, status="failed", error=str(exc), status_text="failed")
            self.log(task_id, f"failed: {exc}")

    def submit_task(self, task: dict):
        request_mode = task["request_mode"]
        headers = self.build_headers(task["auth_mode"], task["api_key"])

        if request_mode == "seedance_special_videos_async":
            reference_images = []
            for path in task["image_paths"][:9]:
                image_url = upload_image_to_imgbb(Path(path))
                asset_id = upload_image_to_seedance_asset(
                    image_url,
                    Path(path).name,
                    task["api_base"],
                    headers,
                    self.request_with_retry,
                )
                reference_images.append(asset_id)
            content = [{"type": "text", "text": task["prompt"]}]
            content.extend(
                {
                    "type": "image_url",
                    "role": "reference_image",
                    "image_url": {"url": image_url},
                }
                for image_url in reference_images
            )
            payload = {
                "model": task["model_id"],
                "ratio": task["aspect_ratio"],
                "duration": int(str(task["seconds"])),
                "generate_audio": True,
                "content": content,
            }
            headers["Content-Type"] = "application/json"
            self.log(
                task["id"],
                "submit payload => "
                f"model={payload['model']}, ratio={payload['ratio']}, duration={payload['duration']}, "
                f"generate_audio=true, reference_images={len(reference_images)}",
            )
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/seedance-special/videos",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("error"):
                raise RuntimeError(str(data.get("error")))
            remote_task_id = data.get("task_id") or data.get("id") or data.get("taskId")
            if not remote_task_id:
                raise RuntimeError(f"missing task id: {data}")
            return remote_task_id

        if request_mode == "aiclub_sora_videos_async":
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "duration": int(str(task["seconds"])),
                "aspect_ratio": task["aspect_ratio"],
                "resolution": "720p",
                "image": process_image_to_data_url(Path(task["image_paths"][0])),
            }
            headers["Content-Type"] = "application/json"
            self.log(
                task["id"],
                "submit payload => "
                f"model={payload['model']}, duration={payload['duration']}, "
                f"aspect_ratio={payload['aspect_ratio']}, resolution=720p, image=1",
            )
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/videos",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("error"):
                error = data["error"]
                if isinstance(error, dict):
                    error = error.get("message") or str(error)
                raise RuntimeError(str(error))
            remote_task_id = data.get("task_id") or data.get("id") or data.get("taskId")
            if not remote_task_id:
                raise RuntimeError(f"missing task id: {data}")
            return remote_task_id

        if request_mode == "luxvid_videos_async":
            reference_images = [upload_image_to_imgbb(Path(path)) for path in task["image_paths"][:9]]
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "duration": int(str(task["seconds"])),
                "ratio": task["aspect_ratio"],
                "resolution": "720p",
                "referenceImages": reference_images,
            }
            if task["model_id"] == "videos":
                payload["autoFace"] = bool(task.get("auto_face"))
            headers["Content-Type"] = "application/json"
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/videos/videos",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("error"):
                raise RuntimeError(str(data.get("error")))
            return data.get("task_id") or data.get("id") or data.get("taskId")

        if request_mode == "xs_sora_videos_async":
            reference_images = [upload_image_to_imgbb(Path(path)) for path in task["image_paths"][:4]]
            image_count = len(reference_images)
            reference_mode = "image_reference"
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "duration": int(str(task["seconds"])),
                "reference_images": reference_images,
                "video_config": {
                    "aspect_ratio": task["aspect_ratio"],
                    "resolution_name": task["resolution"],
                    "reference_mode": reference_mode,
                },
            }
            headers["Content-Type"] = "application/json"
            self.log(
                task["id"],
                "submit payload => "
                f"model={payload.get('model')}, duration={payload.get('duration')}, "
                f"aspect_ratio={task['aspect_ratio']}, resolution={task['resolution']}, "
                f"reference_images={image_count}, reference_mode={reference_mode}"
            )
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/videos",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"???? {response.status_code}: {response.text}")
            data = response.json()
            if data.get("error"):
                error = data.get("error")
                if isinstance(error, dict):
                    error = error.get("message") or str(error)
                raise RuntimeError(error)
            return data.get("task_id") or data.get("id") or data.get("taskId")

        if request_mode == "ycy_video_generations_async":
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "ratio": task["aspect_ratio"],
            }
            headers["Content-Type"] = "application/json"
            self.log(
                task["id"],
                "submit payload => "
                f"model={payload.get('model')}, ratio={payload.get('ratio')}, seconds=15"
            )
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/video/generations",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"YCY submit failed {response.status_code}: {response.text}")
            data = response.json()
            if data.get("error"):
                error = data.get("error")
                if isinstance(error, dict):
                    error = error.get("message") or str(error)
                raise RuntimeError(error)
            return data.get("task_id") or data.get("id") or data.get("taskId")

        if request_mode == "dolo_videos_async":
            image_urls = [upload_image_to_imgbb(Path(path)) for path in task["image_paths"][:9]]
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "duration": int(str(task["seconds"])),
                "ratio": task["aspect_ratio"],
                "images": image_urls,
            }
            headers["Content-Type"] = "application/json"
            self.log(
                task["id"],
                "submit payload => "
                f"model={payload.get('model')}, ratio={payload.get('ratio')}, "
                f"duration={payload.get('duration')}, images={len(image_urls)}"
            )
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/videos",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"dolo submit failed {response.status_code}: {response.text}")
            data = response.json()
            if data.get("error"):
                error = data.get("error")
                if isinstance(error, dict):
                    error = error.get("message") or str(error)
                raise RuntimeError(error)
            return data.get("task_id") or data.get("id") or data.get("taskId")

        if request_mode == "sudashui_videos_async":
            import json
            image_urls = [upload_file_to_sudashui(Path(path), task["api_key"]) for path in task["image_paths"][:4]]
            payload_data = {
                "aspectRatio": task["aspect_ratio"],
                "mode": "references",
            }
            if image_urls:
                payload_data["imageUrls"] = image_urls
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "duration": int(str(task["seconds"])),
                "metadata": {
                    "payload": json.dumps(payload_data, ensure_ascii=False, separators=(",", ":")),
                },
            }
            headers["Content-Type"] = "application/json"
            self.log(
                task["id"],
                "submit payload => "
                f"model={payload.get('model')}, duration={payload.get('duration')}, "
                f"aspectRatio={task['aspect_ratio']}, imageUrls={len(image_urls)}"
            )
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/video/generations",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"sudashui submit failed {response.status_code}: {response.text}")
            data = response.json()
            if data.get("code") and str(data.get("code")).lower() not in ("success", "ok"):
                raise RuntimeError(data.get("message") or str(data))
            if data.get("error"):
                error = data.get("error")
                if isinstance(error, dict):
                    error = error.get("message") or str(error)
                raise RuntimeError(error)
            result = data.get("data") or data
            return result.get("task_id") or result.get("id") or data.get("task_id") or data.get("id") or data.get("taskId")

        if request_mode == "wy_sd2_videos_async":
            image_urls = [upload_image_to_imgbb(Path(path)) for path in task["image_paths"][:9]]
            image_count = len(image_urls)
            if image_count <= 0:
                mode = "text_to_video"
            elif image_count == 1:
                mode = "image_to_video"
            else:
                mode = "reference_to_video"
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "metadata": {
                    "mode": mode,
                    "aspectRatio": task["aspect_ratio"],
                    "resolution": "720p",
                    "duration": int(str(task["seconds"])),
                    "generateAudio": True,
                },
                "referenceImages": image_urls,
                "referenceVideos": [],
                "referenceAudios": [],
            }
            headers["Content-Type"] = "application/json; charset=utf-8"
            self.log(
                task["id"],
                "submit payload => "
                f"model={payload.get('model')}, "
                f"mode={mode}, aspectRatio={task['aspect_ratio']}, "
                f"resolution=720p, duration={task['seconds']}, "
                f"referenceImages={image_count}"
            )
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/videos",
                headers=headers,
                json=payload,
                timeout=120,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"???? {response.status_code}: {response.text}")
            data = response.json()
            if data.get("error"):
                error = data.get("error")
                if isinstance(error, dict):
                    error = error.get("message") or str(error)
                raise RuntimeError(error)
            return data.get("task_id") or data.get("id") or data.get("taskId")

        if request_mode == "grok_imagine_videos_async":
            image_urls = [process_image_to_data_url(Path(path)) for path in task["image_paths"][:7]]
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "seconds": str(task["seconds"]),
                "duration": int(str(task["seconds"])),
                "size": build_grok_imagine_size_value(task["aspect_ratio"]),
            }
            if len(image_urls) == 1:
                payload["image"] = image_urls[0]
            else:
                payload["images"] = image_urls
            headers["Content-Type"] = "application/json"
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/videos",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("task_id") or data.get("id") or data.get("taskId")

        if request_mode == "hancat_videos_async":
            image_urls = [process_image_to_data_url(Path(path)) for path in task["image_paths"][:3]]
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "type": 3,
                "aspect_ratio": task["aspect_ratio"],
                "seconds": "8",
                "images": image_urls,
                "generate_audio": True,
                "negative_prompt": "blur, distortion, low quality",
            }
            headers["Content-Type"] = "application/json"
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/videos",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("task_id") or data.get("id") or data.get("taskId")

        if request_mode == "zcb_veo_videos_async":
            reference_images = [upload_image_to_imgbb(Path(path)) for path in task["image_paths"][:3]]
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "resolution": task["resolution"],
                "aspect_ratio": task["aspect_ratio"],
                "input_reference": reference_images,
            }
            headers["Content-Type"] = "application/json"
            headers["Accept"] = "application/json"
            self.log(
                task["id"],
                "submit payload => "
                f"model={payload.get('model')}, "
                f"aspect_ratio={payload.get('aspect_ratio')}, "
                f"resolution={payload.get('resolution')}, "
                f"input_reference={len(reference_images)}"
            )
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/veo/videos",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("error"):
                raise RuntimeError(str(data.get("error")))
            return data.get("task_id") or data.get("id") or data.get("taskId")

        if request_mode == "sora_vip3_multi_image":
            reference_urls = [process_image_to_data_url(Path(path)) for path in task["image_paths"]]
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "aspect_ratio": task["aspect_ratio"],
                "resolution": task["resolution"],
                "seconds": str(task["seconds"]),
            }
            if len(reference_urls) == 1:
                payload["image_url"] = reference_urls[0]
            elif reference_urls:
                payload["reference_image_urls"] = reference_urls
            headers["Content-Type"] = "application/json"
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/videos",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("task_id") or data.get("id") or data.get("taskId")

        if request_mode == "longxia_videos_async":
            payload = {
                "model": task["model_id"],
                "prompt": task["prompt"],
                "seconds": str(task["seconds"]),
                "size": task["size_value"].replace("*", "x"),
                "generate_audio": True,
                "reference_images": [
                    {
                        "b64_json": load_file_base64(Path(image_path)),
                        "filename": Path(image_path).name,
                    }
                    for image_path in task["image_paths"]
                ],
            }
            headers["Content-Type"] = "application/json"
            response = self.request_with_retry(
                "post",
                f"{task['api_base']}/v1/videos",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("id") or data.get("task_id") or data.get("taskId")

        if request_mode == "videos_async":
            form_data = {"model": task["model_id"], "prompt": task["prompt"]}
            if task["size_value"]:
                form_data["size"] = task["size_value"]
            files = []
            file_handles = []
            try:
                for image_path in task["image_paths"]:
                    handle = open(image_path, "rb")
                    file_handles.append(handle)
                    files.append(("input_reference", (Path(image_path).name, handle, "application/octet-stream")))
                response = self.request_with_retry(
                    "post",
                    f"{task['api_base']}/v1/videos",
                    headers=headers,
                    data=form_data,
                    files=files,
                    timeout=120,
                )
            finally:
                for handle in file_handles:
                    handle.close()
            response.raise_for_status()
            data = response.json()
            return data.get("task_id") or data.get("id") or data.get("taskId")

        content = []
        for image_path in task["image_paths"]:
            content.append({"type": "image_url", "image_url": {"url": process_image_to_data_url(Path(image_path))}})
        content.append({"type": "text", "text": task["prompt"]})
        payload = {"model": task["model_id"], "messages": [{"role": "user", "content": content}]}
        response = self.request_with_retry(
            "post",
            f"{task['api_base']}/v1/generate",
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("task_id") or data.get("id") or data.get("taskId")

    def poll_task(self, task: dict, remote_task_id: str):
        headers = self.build_headers(task["auth_mode"], task["api_key"])
        request_mode = task["request_mode"]
        pulse_progress = 20
        interval = LONGXIA_POLL_INTERVAL_SECONDS if request_mode == "longxia_videos_async" else POLL_INTERVAL_SECONDS

        while True:
            if request_mode in ("seedance_special_videos_async", "luxvid_videos_async", "zcb_veo_videos_async"):
                poll_url = f"{task['api_base']}/v1/result/{remote_task_id}"
            elif request_mode == "xs_sora_videos_async":
                poll_url = f"{task['api_base']}/videos/{remote_task_id}"
            elif request_mode == "ycy_video_generations_async":
                poll_url = f"{task['api_base']}/v1/video/generations/{remote_task_id}"
            elif request_mode == "dolo_videos_async":
                poll_url = f"{task['api_base']}/v1/videos/{remote_task_id}"
            elif request_mode == "sudashui_videos_async":
                poll_url = f"{task['api_base']}/v1/video/generations/{remote_task_id}"
            elif request_mode in ("aiclub_sora_videos_async", "videos_async", "sora_vip3_multi_image", "longxia_videos_async", "grok_imagine_videos_async", "hancat_videos_async", "wy_sd2_videos_async"):
                poll_url = f"{task['api_base']}/v1/videos/{remote_task_id}"
            else:
                poll_url = f"{task['api_base']}/v1/tasks/{remote_task_id}"

            response = self.request_with_retry("get", poll_url, headers=headers, timeout=60)
            if response.status_code == 404 and request_mode == "zcb_veo_videos_async":
                response = self.request_with_retry(
                    "get",
                    f"{task['api_base']}/v1/veo/videos/{remote_task_id}",
                    headers=headers,
                    timeout=60,
                )
            response.raise_for_status()
            raw_data = response.json()
            if request_mode in ("seedance_special_videos_async", "luxvid_videos_async", "zcb_veo_videos_async"):
                data = raw_data.get("data", raw_data) if isinstance(raw_data, dict) else {}
            elif request_mode in ("longxia_videos_async", "sudashui_videos_async"):
                data = raw_data.get("data", raw_data)
            else:
                data = raw_data
            status = str(data.get("status", "")).lower()
            progress = data.get("progress")

            if isinstance(progress, (int, float)):
                self.update(task["id"], progress=max(12, min(95, int(progress))))
            else:
                pulse_progress = min(92, pulse_progress + 6)
                self.update(task["id"], progress=pulse_progress)

            if status in ("queued", "pending"):
                self.update(task["id"], status_text="queued")
            elif status in ("running", "processing", "in_progress"):
                self.update(task["id"], status_text="processing")
            elif status in ("completed", "success", "succeeded", "done"):
                result = data.get("result") or {}
                remote_url = (
                    data.get("video_url")
                    or data.get("url")
                    or data.get("result_url")
                    or result.get("file_url")
                    or result.get("url")
                    or raw_data.get("video_url")
                    or raw_data.get("url")
                )
                remote_url = normalize_video_url(remote_url, task["api_base"])
                if not remote_url:
                    remote_url = normalize_video_url(extract_video_url_recursive(raw_data), task["api_base"])
                if not remote_url:
                    if request_mode == "ycy_video_generations_async":
                        remote_url = f"{task['api_base']}/v1/videos/{remote_task_id}/content"
                    elif request_mode == "sora_vip3_multi_image":
                        remote_url = f"{task['api_base']}/v1/videos/{remote_task_id}/content"
                    elif request_mode == "videos_async":
                        remote_url = f"{task['api_base']}/v1/videos/{remote_task_id}/file"
                    elif request_mode == "dolo_videos_async":
                        remote_url = f"{task['api_base']}/v1/videos/{remote_task_id}/content"
                    elif request_mode == "sudashui_videos_async":
                        remote_url = data.get("result_url") or extract_video_url_recursive(data)
                    elif request_mode in ("grok_imagine_videos_async", "hancat_videos_async", "wy_sd2_videos_async"):
                        remote_url = f"{task['api_base']}/v1/videos/{remote_task_id}"
                    elif request_mode == "xs_sora_videos_async":
                        remote_url = f"{task['api_base']}/videos/{remote_task_id}"
                    elif request_mode == "aiclub_sora_videos_async":
                        remote_url = f"{task['api_base']}/v1/videos/{remote_task_id}/content"
                if not remote_url:
                    raise RuntimeError(f"missing video url: {raw_data}")
                return remote_url
            elif status in ("failed", "failure", "error"):
                error_text = data.get("error")
                if isinstance(error_text, dict):
                    error_text = error_text.get("message") or str(error_text)
                raise RuntimeError(error_text or str(raw_data))

            time.sleep(interval)

    def download_video(self, task: dict, remote_url: str, remote_task_id: str):
        date_folder = datetime.now().strftime("%Y-%m-%d")
        save_dir = OUTPUT_DIR / date_folder
        ensure_dir(save_dir)
        file_name = f"video_{datetime.now().strftime('%H%M%S')}_{remote_task_id[:8]}.mp4"
        local_path = save_dir / file_name

        headers = {"User-Agent": "Mozilla/5.0"}
        if urlparse(remote_url).netloc == urlparse(task["api_base"]).netloc:
            headers.update(self.build_headers(task["auth_mode"], task["api_key"]))

        last_error = None
        for attempt in range(1, DOWNLOAD_RETRIES + 1):
            try:
                response = self.request_with_retry("get", remote_url, headers=headers, stream=True, timeout=120)
                with response:
                    response.raise_for_status()
                    with open(local_path, "wb") as handle:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                handle.write(chunk)
                return local_path
            except (requests_exceptions.RequestException, OSError) as exc:
                last_error = exc
                if attempt >= DOWNLOAD_RETRIES or not self.is_transient_request_error(exc):
                    raise
                time.sleep(RETRY_SLEEP_SECONDS)
        raise last_error


ensure_dir(UPLOAD_DIR)
ensure_dir(OUTPUT_DIR)

app = Flask(__name__)
CORS(app)
TASKS: Dict[str, dict] = {}
TASK_LOCK = threading.Lock()
RUNNER = WebTaskRunner(TASKS, TASK_LOCK)


def safe_remove_path(path_value):
    if not path_value:
        return
    path = Path(path_value)
    try:
        if path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def cleanup_expired_files_once():
    cutoff = time.time() - FILE_RETENTION_SECONDS
    expired_ids = []
    with TASK_LOCK:
        for task_id, task in list(TASKS.items()):
            completed_ts = task.get("completed_ts")
            created_ts = task.get("created_ts") or 0
            if task.get("status") in {"completed", "failed"} and (completed_ts or created_ts) < cutoff:
                expired_ids.append(task_id)
                safe_remove_path(task.get("local_path"))
                upload_parent = Path(task.get("image_paths", [""])[0]).parent if task.get("image_paths") else None
                if upload_parent and str(upload_parent).startswith(str(UPLOAD_DIR)):
                    safe_remove_path(upload_parent)
        for task_id in expired_ids:
            TASKS.pop(task_id, None)

    for root in (OUTPUT_DIR, UPLOAD_DIR):
        if not root.exists():
            continue
        for item in root.iterdir():
            try:
                if item.stat().st_mtime < cutoff:
                    safe_remove_path(item)
            except OSError:
                pass


def cleanup_loop():
    while True:
        cleanup_expired_files_once()
        time.sleep(CLEANUP_INTERVAL_SECONDS)


threading.Thread(target=cleanup_loop, daemon=True).start()


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "name": APP_NAME, "time": now_text()})


@app.get("/api/models")
def models():
    model_data = []
    for item in MODEL_OPTIONS:
        model_family = item["value"]
        model_data.append(
            {
                "label": item["label"],
                "value": model_family,
                "max_images": get_max_images_for_model(model_family),
                "resolutions": get_allowed_resolutions(model_family),
                "seconds_options": get_allowed_seconds(model_family),
                "aspect_ratios": ["16:9", "9:16", "1:1"] if model_family in ("videos_pro", "LuxVid_video", "videos_stable_fast", "wy-sd2", "video-v1-15s", "dolo", "xh-sdas-fast-720p", "xh-sdas-pro-720p") else (["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"] if model_family in ("sora-v4-fast", "sora-v3-pro") else (["16:9", "9:16"] if model_family == "sora-2-pro" or model_family in VEO_STABLE_MODELS else ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"])),
                "needs_api_key": item.get("needs_api_key", False),
            }
        )
    return jsonify({"models": model_data})


@app.get("/api/tasks")
def list_tasks():
    with TASK_LOCK:
        tasks = [serialize_task(task) for task in sorted(TASKS.values(), key=lambda x: x["created_ts"], reverse=True)]
    return jsonify({"tasks": tasks})


@app.get("/api/tasks/<task_id>")
def get_task(task_id: str):
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if not task:
            return jsonify({"error": "task not found"}), 404
        return jsonify(serialize_task(task))


@app.get("/api/tasks/<task_id>/download")
def download_task(task_id: str):
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if not task:
            return jsonify({"error": "task not found"}), 404
        local_path = task.get("local_path")
    if not local_path or not os.path.exists(local_path):
        return jsonify({"error": "video not ready"}), 404
    return send_file(local_path, as_attachment=True, download_name=Path(local_path).name)


@app.get("/api/tasks/<task_id>/images/<int:image_index>")
def get_task_image(task_id: str, image_index: int):
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if not task:
            return jsonify({"error": "task not found"}), 404
        image_paths = task.get("image_paths") or []
    if image_index < 0 or image_index >= len(image_paths):
        return jsonify({"error": "image not found"}), 404
    image_path = image_paths[image_index]
    if not os.path.exists(image_path):
        return jsonify({"error": "image file missing"}), 404
    return send_file(image_path)


@app.post("/api/tasks/<task_id>/rerun")
def rerun_task(task_id: str):
    with TASK_LOCK:
        source = TASKS.get(task_id)
        if not source:
            return jsonify({"error": "task not found"}), 404
        source_copy = dict(source)

    source_images = source_copy.get("image_paths") or []
    if not source_images:
        return jsonify({"error": "source task has no images"}), 400

    request_id = uuid.uuid4().hex[:10]
    task_upload_dir = UPLOAD_DIR / request_id
    ensure_dir(task_upload_dir)
    image_paths: List[str] = []
    try:
        for index, image_path in enumerate(source_images, start=1):
            src = Path(image_path)
            if not src.exists():
                raise FileNotFoundError(f"source image missing: {src.name}")
            suffix = src.suffix or ".jpg"
            dst_name = secure_filename(src.name) or f"image_{index}{suffix}"
            dst = task_upload_dir / dst_name
            if dst.exists():
                dst = task_upload_dir / f"image_{index}{suffix}"
            shutil.copy2(src, dst)
            image_paths.append(str(dst))
    except Exception as exc:
        safe_remove_path(task_upload_dir)
        return jsonify({"error": str(exc)}), 400

    task = {
        "id": request_id,
        "display_id": f"task_{request_id}",
        "remote_task_id": "",
        "created_at": now_text(),
        "created_ts": time.time(),
        "status": "queued",
        "status_text": "queued",
        "progress": 0,
        "error": "",
        "model_family": source_copy.get("model_family"),
        "model_id": source_copy.get("model_id"),
        "aspect_ratio": source_copy.get("aspect_ratio"),
        "resolution": source_copy.get("resolution"),
        "seconds": source_copy.get("seconds"),
        "auto_face": bool(source_copy.get("auto_face")),
        "prompt": source_copy.get("prompt", ""),
        "image_paths": image_paths,
        "size_value": source_copy.get("size_value", ""),
        "api_base": source_copy.get("api_base"),
        "api_key": source_copy.get("api_key"),
        "auth_mode": source_copy.get("auth_mode"),
        "request_mode": source_copy.get("request_mode"),
        "remote_url": "",
        "local_path": "",
        "duration_seconds": None,
        "logs": [f"[{short_now()}] task recreated from {source_copy.get('display_id') or task_id}"],
    }

    thread = threading.Thread(target=RUNNER.run_task, args=(request_id,), daemon=True)
    task["thread"] = thread
    with TASK_LOCK:
        TASKS[request_id] = task
    thread.start()
    return jsonify(serialize_task(task)), 202


@app.post("/api/tasks")
def create_task():
    model_family = (request.form.get("model_family") or "").strip()
    prompt = (request.form.get("prompt") or "").strip()
    aspect_ratio = (request.form.get("aspect_ratio") or "16:9").strip()
    resolution = (request.form.get("resolution") or "720p").strip()
    seconds = str(request.form.get("seconds") or "5").strip()
    files = request.files.getlist("images")
    manual_api_key = (request.form.get("api_key") or "").strip()
    auto_face = str(request.form.get("auto_face") or "").strip().lower() in ("1", "true", "yes", "on")

    if not model_family:
        return jsonify({"error": "missing model_family"}), 400
    if model_family not in {item["value"] for item in MODEL_OPTIONS}:
        return jsonify({"error": "unsupported model_family"}), 400
    if not prompt:
        return jsonify({"error": "missing prompt"}), 400

    max_images = get_max_images_for_model(model_family)
    if max_images > 0 and not files:
        return jsonify({"error": "at least one reference image is required"}), 400
    if max_images == 0 and files:
        return jsonify({"error": "this model does not accept reference images"}), 400
    if len(files) > max_images:
        return jsonify({"error": f"model allows at most {max_images} images"}), 400

    allowed_resolutions = get_allowed_resolutions(model_family)
    if resolution not in allowed_resolutions:
        return jsonify({"error": f"resolution must be one of {allowed_resolutions}"}), 400

    request_id = uuid.uuid4().hex[:10]
    task_upload_dir = UPLOAD_DIR / request_id
    ensure_dir(task_upload_dir)
    image_paths: List[str] = []
    for index, file_storage in enumerate(files, start=1):
        filename = secure_filename(file_storage.filename or f"image_{index}.jpg")
        if not filename:
            filename = f"image_{index}.jpg"
        save_path = task_upload_dir / filename
        file_storage.save(save_path)
        image_paths.append(str(save_path))

    model_id = build_model_id(model_family, aspect_ratio, resolution)
    backend = get_backend_config(model_family)
    size_value = (
        ""
        if model_family in PROMPT_RATIO_MODELS
        or model_family in (
            "videos",
            "videos_pro",
            "wy-sd2",
            "sora-v4-fast",
            "sora-v3-pro",
            "sora-2-pro",
            "video-v1-15s",
            "dolo",
            "xh-sdas-fast-720p",
            "xh-sdas-pro-720p",
            "LuxVid_video",
            "videos_stable_fast",
            "grok-imagine-video-1.5-preview",
            "veo3.1-components",
            "veo3.1-fast-components",
            "veo_3_1_pro_stable",
            "veo_3_1_fast",
            "veo_3_1_pro",
        )
        else build_size_value(aspect_ratio, resolution)
    )
    prompt = build_request_prompt(model_family, prompt, aspect_ratio)

    task = {
        "id": request_id,
        "display_id": f"task_{request_id}",
        "remote_task_id": "",
        "created_at": now_text(),
        "created_ts": time.time(),
        "status": "queued",
        "status_text": "queued",
        "progress": 0,
        "error": "",
        "model_family": model_family,
        "model_id": model_id,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "seconds": seconds,
        "auto_face": auto_face if model_family == "videos" else False,
        "prompt": prompt,
        "image_paths": image_paths,
        "size_value": size_value,
        "api_base": backend["api_base"],
        "api_key": backend["api_key"],
        "auth_mode": backend["auth_mode"],
        "request_mode": backend["request_mode"],
        "remote_url": "",
        "local_path": "",
        "duration_seconds": None,
        "logs": [f"[{short_now()}] task created"],
    }

    thread = threading.Thread(target=RUNNER.run_task, args=(request_id,), daemon=True)
    task["thread"] = thread
    with TASK_LOCK:
        TASKS[request_id] = task
    thread.start()
    return jsonify(serialize_task(task)), 202


if __name__ == "__main__":
    app.run(
        host=env_value("FLASK_HOST", "0.0.0.0"),
        port=int(env_value("FLASK_PORT", "5000")),
        debug=env_value("FLASK_DEBUG", "0") == "1",
    )

