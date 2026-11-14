#!/usr/bin/env python3
"""Download an official Minecraft game directory from Mojang's version manifest."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
MAX_METADATA_BYTES = 64 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 2 * 1024**3
CHUNK_SIZE = 1024 * 1024
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
    "COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³",
}


def _safe_relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError(f"Unsafe Mojang download path: {value!r}")
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Unsafe Mojang download path: {value!r}")
    if any(
        part.endswith((".", " "))
        or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
        or part.split(".", 1)[0].rstrip(" .").upper() in WINDOWS_RESERVED_NAMES
        for part in path.parts
    ):
        raise ValueError(f"Non-portable Mojang download path: {value!r}")
    return pathlib.Path(*path.parts)


def _validate_url(url):
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    official_host = host == "mojang.com" or host.endswith(".mojang.com") or host == "minecraft.net" or host.endswith(".minecraft.net")
    if parsed.scheme != "https" or not official_host:
        raise ValueError(f"Refusing non-official Mojang download URL: {url!r}")
    return url


def _read_url(url, expected_size=None, expected_sha1=None, max_bytes=MAX_DOWNLOAD_BYTES):
    _validate_url(url)
    last_error = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Horizon-Native-Instance-Builder/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                _validate_url(response.geturl())
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > max_bytes:
                    raise ValueError(f"Download exceeds size limit: {url}")
                chunks = []
                total = 0
                digest = hashlib.sha1()
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"Download exceeds size limit: {url}")
                    chunks.append(chunk)
                    digest.update(chunk)
            if expected_size is not None and total != expected_size:
                raise ValueError(f"Size mismatch for {url}: expected {expected_size}, got {total}")
            actual_sha1 = digest.hexdigest()
            if expected_sha1 and actual_sha1.lower() != expected_sha1.lower():
                raise ValueError(f"SHA-1 mismatch for {url}: expected {expected_sha1}, got {actual_sha1}")
            return b"".join(chunks)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Could not download {url} after 3 attempts: {last_error}") from last_error


def _write_verified(root, relative, url, size=None, sha1=None):
    destination = root / _safe_relative_path(relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _validate_url(url)
    last_error = None
    for attempt in range(3):
        temporary = destination.with_name(destination.name + ".part")
        digest = hashlib.sha1()
        total = 0
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Horizon-Native-Instance-Builder/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response, temporary.open("wb") as output:
                _validate_url(response.geturl())
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > MAX_DOWNLOAD_BYTES:
                    raise ValueError(f"Download exceeds size limit: {url}")
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise ValueError(f"Download exceeds size limit: {url}")
                    output.write(chunk)
                    digest.update(chunk)
            if size is not None and total != size:
                raise ValueError(f"Size mismatch for {url}: expected {size}, got {total}")
            if sha1 and digest.hexdigest().lower() != sha1.lower():
                raise ValueError(f"SHA-1 mismatch for {url}: expected {sha1}, got {digest.hexdigest()}")
            temporary.replace(destination)
            return destination
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as error:
            last_error = error
            temporary.unlink(missing_ok=True)
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    raise RuntimeError(f"Could not download {url} after 3 attempts: {last_error}") from last_error


def _metadata_entry(version_id, versions):
    if not isinstance(version_id, str) or not re.fullmatch(r"[A-Za-z0-9._+-]+", version_id):
        raise ValueError(f"Invalid Minecraft version ID: {version_id!r}")
    for entry in versions:
        if entry.get("id") == version_id:
            return entry
    raise ValueError(f"Minecraft version {version_id!r} is not present in Mojang's official manifest")


def _download_version(version_id, manifest_versions, root, visited, libraries, asset_indexes):
    if version_id in visited:
        return
    visited.add(version_id)
    entry = _metadata_entry(version_id, manifest_versions)
    metadata_bytes = _read_url(entry["url"], entry.get("size"), entry.get("sha1"), MAX_METADATA_BYTES)
    metadata = json.loads(metadata_bytes)
    if not isinstance(metadata, dict) or metadata.get("id") != version_id:
        raise ValueError(f"Mojang metadata ID mismatch for {version_id}")

    metadata_path = root / "versions" / version_id / f"{version_id}.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_bytes(json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8") + b"\n")

    client = metadata.get("downloads", {}).get("client") if isinstance(metadata.get("downloads"), dict) else None
    if client:
        _write_verified(root, f"versions/{version_id}/{version_id}.jar", client["url"], client.get("size"), client.get("sha1"))
    elif not metadata.get("inheritsFrom"):
        raise ValueError(f"Mojang metadata for {version_id} has no client download")

    asset_index = metadata.get("assetIndex")
    if asset_index:
        index_id = asset_index.get("id")
        if not isinstance(index_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", index_id):
            raise ValueError(f"Invalid asset index ID in {version_id}")
        index_path = f"assets/indexes/{index_id}.json"
        index_bytes = _read_url(asset_index["url"], asset_index.get("size"), asset_index.get("sha1"), MAX_METADATA_BYTES)
        (root / index_path).parent.mkdir(parents=True, exist_ok=True)
        (root / index_path).write_bytes(index_bytes)
        index = json.loads(index_bytes)
        objects = index.get("objects") if isinstance(index, dict) else None
        if not isinstance(objects, dict):
            raise ValueError(f"Invalid asset index for {version_id}")
        asset_indexes[index_id] = objects

    version_libraries = metadata.get("libraries", [])
    if not isinstance(version_libraries, list):
        raise ValueError(f"Invalid libraries list in {version_id}")
    libraries.extend(version_libraries)

    parent = metadata.get("inheritsFrom")
    if parent:
        _download_version(parent, manifest_versions, root, visited, libraries, asset_indexes)


def _library_downloads(library):
    downloads = library.get("downloads")
    if isinstance(downloads, dict):
        artifact = downloads.get("artifact")
        if artifact:
            yield artifact
        classifiers = downloads.get("classifiers")
        if isinstance(classifiers, dict):
            for item in classifiers.values():
                if item:
                    yield item
        return

    # Legacy Maven coordinates remain supported for older official versions.
    coordinate = library.get("name")
    if not isinstance(coordinate, str):
        return
    extension = "jar"
    if "@" in coordinate:
        coordinate, extension = coordinate.rsplit("@", 1)
    parts = coordinate.split(":")
    if len(parts) not in (3, 4):
        raise ValueError(f"Unsupported legacy Mojang library coordinate: {library.get('name')}")
    group, artifact, version = parts[:3]
    classifier = parts[3] if len(parts) == 4 else ""
    relative = "/".join(group.split(".")) + f"/{artifact}/{version}/{artifact}-{version}"
    if classifier:
        relative += f"-{classifier}"
    relative += f".{extension}"
    base = library.get("url") or "https://libraries.minecraft.net/"
    yield {"path": relative, "url": urllib.parse.urljoin(base.rstrip("/") + "/", relative)}


def _download_asset(root, logical_name, record):
    sha1 = record.get("hash")
    if not isinstance(sha1, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha1):
        raise ValueError(f"Invalid Mojang asset SHA-1 for {logical_name}")
    relative = f"assets/objects/{sha1[:2].lower()}/{sha1.lower()}"
    url = f"https://resources.download.minecraft.net/{sha1[:2].lower()}/{sha1.lower()}"
    destination = root / relative
    if destination.is_file():
        digest = hashlib.sha1()
        with destination.open("rb") as existing:
            for chunk in iter(lambda: existing.read(CHUNK_SIZE), b""):
                digest.update(chunk)
        if digest.hexdigest() == sha1.lower():
            return relative
    _write_verified(root, relative, url, record.get("size"), sha1)
    return relative


def download_game(version, output_zip):
    manifest_bytes = _read_url(MANIFEST_URL, max_bytes=MAX_METADATA_BYTES)
    manifest = json.loads(manifest_bytes)
    versions = manifest.get("versions")
    if not isinstance(versions, list):
        raise ValueError("Mojang version manifest has no versions list")
    if version == "latest-release":
        version_id = manifest["latest"]["release"]
    elif version == "latest-snapshot":
        version_id = manifest["latest"]["snapshot"]
    else:
        version_id = version
    _metadata_entry(version_id, versions)

    output_zip = pathlib.Path(output_zip)
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="horizon-minecraft-") as temporary:
        root = pathlib.Path(temporary) / "game"
        root.mkdir()
        visited, libraries, asset_indexes = set(), [], {}
        _download_version(version_id, versions, root, visited, libraries, asset_indexes)

        # Include official artifacts and all declared classifier variants. This deliberately
        # covers both Windows and Linux native-build runners without relying on host OS rules.
        unique_downloads = {}
        for library in libraries:
            for artifact in _library_downloads(library):
                relative = artifact.get("path")
                url = artifact.get("url")
                if relative and url:
                    safe = _safe_relative_path(relative).as_posix()
                    previous = unique_downloads.get(safe)
                    if previous and previous.get("sha1") != artifact.get("sha1"):
                        raise ValueError(f"Conflicting Mojang library metadata for {safe}")
                    if previous is None:
                        unique_downloads[safe] = artifact
        for relative, artifact in unique_downloads.items():
            _write_verified(root, f"libraries/{relative}", artifact["url"], artifact.get("size"), artifact.get("sha1"))

        all_assets = {}
        for objects in asset_indexes.values():
            for logical_name, record in objects.items():
                asset_hash = record.get("hash") if isinstance(record, dict) else None
                if asset_hash:
                    previous = all_assets.get(asset_hash.lower())
                    if previous and previous[1].get("size") != record.get("size"):
                        raise ValueError(f"Conflicting Mojang asset metadata for {logical_name}")
                    all_assets[asset_hash.lower()] = (logical_name, record)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(_download_asset, root, name, record)
                for name, record in all_assets.values()
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        staged_zip = None
        try:
            # Build beside the destination, then publish with one same-filesystem replace.
            # A failed ZIP write must never destroy a previously usable instance archive.
            with tempfile.NamedTemporaryFile(
                prefix=f".{output_zip.name}.",
                suffix=".part",
                dir=output_zip.parent,
                delete=False,
            ) as temporary_zip:
                staged_zip = pathlib.Path(temporary_zip.name)
            with zipfile.ZipFile(
                staged_zip, "w", compression=zipfile.ZIP_STORED, allowZip64=True
            ) as archive:
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(root).as_posix())
            with staged_zip.open("rb+") as completed_zip:
                completed_zip.flush()
                os.fsync(completed_zip.fileno())
            os.replace(staged_zip, output_zip)
            staged_zip = None
        finally:
            if staged_zip is not None:
                staged_zip.unlink(missing_ok=True)
    print(f"Downloaded official Minecraft {version_id} game files to {output_zip}")
    return version_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="latest-release", help="Mojang version ID, latest-release, or latest-snapshot")
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("input/minecraft/minecraft.zip"))
    args = parser.parse_args()
    try:
        download_game(args.version, args.output)
    except (KeyError, TypeError, json.JSONDecodeError, ValueError, RuntimeError, OSError) as error:
        raise SystemExit(f"Minecraft download failed: {error}") from error


if __name__ == "__main__":
    main()
