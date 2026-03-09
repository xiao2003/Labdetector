from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    PROJECT_ROOT / "launcher.py",
    PROJECT_ROOT / "neurolab_hub.spec",
    PROJECT_ROOT / "pc",
    PROJECT_ROOT / "scripts",
]
EXCLUDED_PARTS = {"APP", "python_runtime", "training_runtime", ".pyi_work", ".pyi_dist", "__pycache__"}
VALID_SUFFIXES = {".py", ".ps1", ".spec"}


def has_mojibake(line: str) -> bool:
    return any(0xC0 <= ord(ch) <= 0xFF for ch in line)


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for target in TARGETS:
        if target.is_file():
            files.append(target)
            continue
        for path in target.rglob("*"):
            if any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            if path.suffix.lower() in VALID_SUFFIXES:
                files.append(path)
    return files


def scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        return [(0, f"UTF-8 decode failed: {exc}")]

    hits: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, start=1):
        if has_mojibake(line):
            hits.append((line_no, line.encode("unicode_escape").decode()))
    return hits


def main() -> int:
    failures: list[tuple[Path, int, str]] = []
    for path in iter_source_files():
        for line_no, line in scan_file(path):
            failures.append((path, line_no, line))

    if not failures:
        print("Encoding check passed.")
        return 0

    print("Detected possible source mojibake. Build aborted.")
    for path, line_no, line in failures:
        location = f"{path.relative_to(PROJECT_ROOT)}:{line_no}" if line_no else str(path.relative_to(PROJECT_ROOT))
        print(f"{location}: {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
