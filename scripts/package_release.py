"""Package application sources and explicit release evidence, excluding runtimes/profiles."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    dist = ROOT / "dist"
    archive = dist / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    for name in ("README.md", "VALIDATION.md", "Granger-OSINT-source.zip"):
        existing = dist / name
        backup = archive / ("before-search-overhaul-" + name)
        if existing.is_file() and not backup.exists():
            shutil.copy2(existing, backup)
    binary_hash = hashlib.sha256((dist / "Granger-OSINT.exe").read_bytes()).hexdigest()
    (dist / "Granger-OSINT.sha256").write_text(binary_hash + "  Granger-OSINT.exe\n", encoding="ascii")
    for name in ("README.md", "VALIDATION.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, dist / name)
    shutil.copytree(ROOT / "docs", dist / "docs", dirs_exist_ok=True)
    files = set()
    for name in ("main.py", "Granger-OSINT.spec", "GrangerPet.spec", "build.ps1", "requirements.txt", "requirements-dev.txt",
                 "README.md", "VALIDATION.md", "THIRD_PARTY_NOTICES.md", ".gitignore", ".gitattributes", ".env.example", "pytest.ini"):
        path = ROOT / name
        if path.is_file():
            files.add(path)
    for name in ("grangerpet", "scripts", "tests", "docs", "resources", ".github", "frontend"):
        for path in (ROOT / name).rglob("*"):
            if path.is_file() and not any(part in path.parts for part in ("__pycache__", "node_modules", ".vite", ".cache")) and path.suffix not in (".pyc", ".pyo", ".tsbuildinfo"):
                files.add(path)
    qa = ROOT / "output/upgrade-qa"
    for name in ("baseline.json", "preservation.json", "profile-preservation.json", "candidate-findings.json", "frozen-sources.json", "frozen-assets.json", "release-summary.json",
                 "secret-scan.json", "freeze-verified.log", "smoke-verified.log", "tests-verified.log", "frontend-package-tests.log", "frontend-package-build.log", "git-publication.json"):
        path = qa / name
        if path.is_file():
            files.add(path)
    summary = json.loads((qa / "release-summary.json").read_text(encoding="utf-8"))
    for name in summary.get("evidence_directories", []):
        if Path(name).name != name:
            raise ValueError("Evidence must be a direct QA subdirectory")
        for path in (qa / name).iterdir() if (qa / name).is_dir() else ():
            if path.is_file() and path.suffix in (".json", ".jsonl", ".png", ".md"):
                files.add(path)
    files.add(dist / "binarysmoke.json")
    temporary = dist / "Granger-OSINT-source.pending.zip"
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(files):
            bundle.write(path, "Granger-OSINT/" + path.relative_to(ROOT).as_posix())
    temporary.replace(dist / "Granger-OSINT-source.zip")
    print(f"Packaged {len(files)} source/evidence files; EXE SHA-256 {binary_hash}")


if __name__ == "__main__":
    main()
