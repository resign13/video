"""Package only the desktop binary and usage guide, then publishable metadata."""
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("desktop_release", ROOT / "desktop_update.py")
updates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updates)


def package():
    package_path = ROOT / "dist.zip"
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in (updates.EXE_NAME, updates.NOTES_NAME):
            archive.write(ROOT / "dist" / name, arcname=name)
    publish_dir = ROOT / "web/output/desktop-release"
    release_dir = publish_dir / "releases"
    release_dir.mkdir(parents=True, exist_ok=True)
    filename = f"AI-Video-{updates.APP_VERSION}.zip"
    shutil.copyfile(package_path, release_dir / filename)
    manifest = {"version": updates.APP_VERSION, "download_url": updates.RELEASE_ORIGIN + "/desktop/releases/" + filename,
                "size": package_path.stat().st_size, "notes": [
                    "全新浅色工作台，按步骤组织参数与素材，预览、任务历史和详情分区展示。",
                    "新增 MEAICC mx-h3 与 sd-2.5-d1-720，复用 MEAICC Key。",
                    "新增独立的渠道可用性模块，客易云仅显示视频规格。",
                    "新增软件更新按钮，支持本地替换和自动重启，保留已保存的 Key 与下载路径。"]}
    (publish_dir / "latest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Packaged desktop {updates.APP_VERSION}: {package_path} ({manifest['size']} bytes)")


if __name__ == "__main__":
    package()
