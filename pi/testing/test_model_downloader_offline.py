from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


PI_ROOT = Path(__file__).resolve().parents[1]
MODEL_DOWNLOADER_PATH = PI_ROOT / "tools" / "model_downloader.py"


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OfflineModelDownloaderTest(unittest.TestCase):
    def test_offline_model_can_be_restored_without_network(self) -> None:
        workspace = Path(tempfile.mkdtemp(prefix="neurolab_model_test_"))
        try:
            copied_root = workspace / "pi"
            shutil.copytree(PI_ROOT, copied_root, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))

            offline_model_dir = copied_root / "offline" / "models" / "vosk-model-small-cn-0.22"
            offline_model_dir.mkdir(parents=True, exist_ok=True)
            (offline_model_dir / "am").write_text("ok", encoding="utf-8")

            target_dir = copied_root / "voice" / "model"
            if target_dir.exists():
                shutil.rmtree(target_dir)

            module = _load_module("pi_model_downloader_offline_test", copied_root / "tools" / "model_downloader.py")
            ok = bool(module.check_and_download_vosk(str(target_dir), allow_download=False))

            self.assertTrue(ok)
            self.assertTrue((target_dir / "am").exists())
        finally:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
