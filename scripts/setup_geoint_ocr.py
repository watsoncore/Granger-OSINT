"""Fetch a portable OCR runtime from MSYS2; never run an installer.

Development/release preparation only, never called by the application. Package
archives are checked against the official HTTPS repository database SHA-256.
Only PE dependencies of tesseract.exe, language data and licences are copied.
No registry, services, global PATH or other applications are modified.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
from urllib.parse import urlsplit

import httpx
import pefile

REPO = "https://repo.msys2.org/mingw/ucrt64/"
MODEL_API = "https://api.github.com/repos/tesseract-ocr/tessdata_fast/commits/main"


def download(client, url, target, expected=None):
    if target.is_file() and (expected is None or hashlib.sha256(target.read_bytes()).hexdigest() == expected):
        return target.read_bytes()
    data = bytearray()
    with client.stream("GET", url) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > 150 * 1024 * 1024:
                raise RuntimeError("Archive exceeds download limit")
    digest = hashlib.sha256(data).hexdigest()
    if expected and digest != expected:
        raise RuntimeError("Official repository checksum mismatch")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return bytes(data)


def prepare(root, refresh=False):
    cache = root / "output" / "geoint-ocr-downloads"
    candidates = cache / "candidates"
    destination = root / "resources" / "ocr"
    candidates.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    lock_path = destination / "provenance.json"
    locked = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() and not refresh else None
    with httpx.Client(follow_redirects=True, timeout=60, headers={"User-Agent": "Granger-OSINT-OCR-Packaging/1 (+https://github.com/watsoncore/Granger-OSINT)"}) as client:
        # A checked-in manifest is a lock. --refresh is an explicit upgrade.
        if locked:
            database = None
        else:
            response = client.get(REPO + "ucrt64.db")
            response.raise_for_status()
            database = response.content
            (cache / "ucrt64.db").write_bytes(database)
        packages = {}
        with tarfile.open(fileobj=io.BytesIO(database), mode="r:*") if database else nullcontext([]) as archive:
            for member in archive:
                if not member.isfile() or not member.name.endswith("/desc"):
                    continue
                text = archive.extractfile(member).read().decode("utf-8")
                fields = {}
                for block in text.split("\n\n"):
                    lines = block.strip().splitlines()
                    if lines and lines[0].startswith("%"):
                        fields[lines[0].strip("%")] = lines[1:]
                if fields.get("NAME"):
                    packages[fields["NAME"][0]] = fields
        if locked:
            for item in locked["packages"]:
                url = urlsplit(item["url"])
                if url.scheme != "https" or url.hostname not in ("repo.msys2.org", "mirror.msys2.org"):
                    raise RuntimeError("Lock contains an unexpected package origin")
                packages[item["name"]] = {"NAME": [item["name"]], "VERSION": [item["version"]],
                                          "FILENAME": [Path(url.path).name], "SHA256SUM": [item["sha256"]]}
        providers = {}
        for package_name, fields in packages.items():
            for provided in fields.get("PROVIDES", []):
                provided = provided.split("=", 1)[0]
                providers.setdefault(provided, package_name)
        required, queue = {}, list(packages) if locked else ["mingw-w64-ucrt-x86_64-tesseract-ocr"]
        while queue:
            name = queue.pop()
            for operator in (">", "<", "="):
                name = name.split(operator, 1)[0]
            if name not in packages and name in providers:
                name = providers[name]
            if name in required:
                continue
            if name not in packages:
                raise RuntimeError("Unresolved runtime package: " + name)
            required[name] = packages[name]
            queue.extend(packages[name].get("DEPENDS", []))
        provenance = {"repository": REPO, "repository_db_sha256": locked["repository_db_sha256"] if locked else hashlib.sha256(database).hexdigest(), "packages": [], "files": []}
        for name, fields in sorted(required.items()):
            filename, digest = fields["FILENAME"][0], fields["SHA256SUM"][0]
            print("Fetching", name, flush=True)
            data = download(client, REPO + filename, cache / filename, digest)
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
                for member in archive:
                    if not member.isfile() or member.size > 100 * 1024 * 1024:
                        continue
                    parts = Path(member.name).parts
                    # No archive extraction method can introduce traversal/symlinks.
                    if ".." in parts or member.name.startswith(("/", "\\")):
                        raise RuntimeError("Unsafe package path")
                    if member.name.startswith("ucrt64/bin/") and (member.name.endswith(".dll") or Path(member.name).name == "tesseract.exe"):
                        (candidates / Path(member.name).name).write_bytes(archive.extractfile(member).read())
                    elif member.name.startswith("ucrt64/share/licenses/"):
                        target = destination / "licenses" / Path(*parts[3:])
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.extractfile(member).read())
                    elif member.name == "ucrt64/share/tessdata/configs/tsv":
                        target = destination / "tessdata" / "configs" / "tsv"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.extractfile(member).read())
            provenance["packages"].append({"name": name, "version": fields["VERSION"][0], "url": REPO + filename, "sha256": digest})
        available = {path.name.lower(): path for path in candidates.iterdir() if path.is_file()}
        selected, queue, external = set(), ["tesseract.exe"], set()
        while queue:
            name = queue.pop().lower()
            if name in selected:
                continue
            path = available.get(name)
            if path is None:
                external.add(name)
                continue
            selected.add(name)
            binary = pefile.PE(str(path), fast_load=False)
            for entry in list(getattr(binary, "DIRECTORY_ENTRY_IMPORT", [])) + list(getattr(binary, "DIRECTORY_ENTRY_DELAY_IMPORT", [])):
                queue.append(entry.dll.decode("ascii").lower())
            binary.close()
            shutil.copy2(path, destination / path.name)
        # MSYS2 packages list only runtime dependencies; missing library imports must
        # resolve to Windows system libraries, never to the developer's PATH.
        provenance["system_imports"] = sorted(external)
        commit = locked["models_commit"] if locked else client.get(MODEL_API).json()["sha"]
        provenance["models_commit"] = commit
        for filename in ("eng.traineddata", "rus.traineddata", "LICENSE"):
            url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{commit}/{filename}"
            target = destination / ("tessdata" if filename.endswith(".traineddata") else "licenses/tessdata_fast") / filename
            expected = next((item["sha256"] for item in locked["files"] if item["path"] == target.relative_to(destination).as_posix()), None) if locked else None
            data = download(client, url, cache / (commit + "-" + filename), expected)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for path in sorted(destination.rglob("*")):
            if path.is_file() and path.name != "provenance.json":
                provenance["files"].append({"path": path.relative_to(destination).as_posix(), "bytes": path.stat().st_size,
                                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        (destination / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"binaries": len(selected), "packages": len(required), "destination": str(destination),
                          "bytes": sum(p.stat().st_size for p in destination.rglob("*") if p.is_file())}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--refresh", action="store_true", help="Explicitly upgrade from the current MSYS2 repository instead of reproducing provenance.json")
    args = parser.parse_args()
    prepare(args.root.resolve(), args.refresh)
