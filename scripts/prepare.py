#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import unicodedata
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INSTANCE = ROOT / "input/instance/instance.zip"
DEFAULT_MINECRAFT = ROOT / "input/minecraft/minecraft.zip"
DEFAULT_MODS = ROOT / "input/mods"
REPORT = ROOT / "build-report"
MAX_ARCHIVE_ENTRIES = 100_000
MAX_MEMBER_UNCOMPRESSED_BYTES = 2 * 1024**3
MAX_TOTAL_UNCOMPRESSED_BYTES = 8 * 1024**3

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
    "COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³",
}


def _portable_windows_component(part):
    """Reject names that alias devices or alternate streams on Windows."""
    stem = part.split(".", 1)[0].rstrip(" .").upper()
    return (
        bool(part)
        and not part.endswith((" ", "."))
        and not any(ord(char) < 32 or char in '<>:"|?*' for char in part)
        and stem not in WINDOWS_RESERVED_NAMES
    )




def _collision_key(value):
    """Normalize canonical Unicode equivalents before case-insensitive comparison."""
    normalized = unicodedata.normalize("NFC", value)
    return unicodedata.normalize("NFC", normalized.casefold())


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_minecraft_root(names):
    candidates = set()
    for name in names:
        normalized = name.replace(chr(92), "/")
        path = pathlib.PurePosixPath(normalized)
        parts = path.parts
        for index in range(len(parts) - 2):
            if (parts[index] == "versions"
                    and parts[index + 1]
                    and pathlib.PurePosixPath(parts[index + 2]).name
                    == parts[index + 1] + ".json"):
                candidates.add("/".join(parts[:index]))
    if not candidates:
        raise ValueError(
            "Minecraft ZIP must contain a complete game directory with "
            "versions/<version>/<version>.json. A Horizon data backup or "
            "Modrinth/CurseForge manifest-only export is not a Minecraft game archive."
        )
    ranked = sorted(
        candidates,
        key=lambda root: (
            sum(1 for name in names
                if name.replace(chr(92), "/").startswith(
                    (root + "/" if root else "") + "versions/"
                ) and name.endswith(".json")),
            root,
        ),
        reverse=True,
    )
    if len(ranked) > 1:
        counts = [
            sum(1 for name in names
                if name.replace(chr(92), "/").startswith(
                    (root + "/" if root else "") + "versions/"
                ) and name.endswith(".json"))
            for root in ranked[:2]
        ]
        if counts[0] == counts[1]:
            raise ValueError(
                "Minecraft ZIP contains multiple equally plausible game roots; "
                "export one game directory per ZIP."
            )
    return ranked[0] or "."


def validate_minecraft_layout(names):
    """Require the game files the native preparer actually consumes."""
    root = discover_minecraft_root(names)
    prefix = "" if root == "." else root.rstrip("/") + "/"
    scoped = {
        name[len(prefix):]
        for name in names
        if name.startswith(prefix)
    }
    versions = set()
    for name in scoped:
        parts = pathlib.PurePosixPath(name).parts
        if (len(parts) == 3 and parts[0] == "versions"
                and parts[2] == parts[1] + ".json"):
            versions.add(parts[1])
    if not versions:
        raise ValueError("Minecraft game root has no versions/<version>/<version>.json metadata.")
    missing = []
    if not any(name.startswith("assets/indexes/") and name.endswith(".json") for name in scoped):
        missing.append("assets/indexes/*.json")
    if not any(name.startswith("assets/objects/") for name in scoped):
        missing.append("assets/objects/")
    if not any(name.startswith("libraries/") for name in scoped):
        missing.append("libraries/")
    if missing:
        raise ValueError(
            "Minecraft ZIP is incomplete; missing " + ", ".join(missing)
            + ". Supply a full game directory, not only version metadata or a launcher backup."
        )
    return root



def validate_minecraft_archive(path, names):
    """Validate real files and the asset-index references, not just directory names."""
    root = discover_minecraft_root(names)
    prefix = "" if root == "." else root.rstrip("/") + "/"
    with zipfile.ZipFile(path) as archive:
        entries = {
            info.filename.replace(chr(92), "/"): info
            for info in archive.infolist()
            if not info.is_dir()
        }

        def read_json(relative, limit):
            name = prefix + relative
            info = entries.get(name)
            if info is None or info.file_size <= 0:
                raise ValueError(f"Minecraft ZIP is missing a non-empty {relative}.")
            if info.file_size > limit:
                raise ValueError(f"Minecraft metadata is unexpectedly large: {relative}.")
            try:
                return json.loads(archive.read(info))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(f"Minecraft metadata is not valid JSON: {relative}.") from error

        version_files = sorted(
            name for name in entries
            if name.startswith(prefix + "versions/")
            and len(pathlib.PurePosixPath(name[len(prefix):]).parts) == 3
            and name.endswith(".json")
        )
        matching_indexes = set()
        for version_file in version_files:
            relative_version = version_file[len(prefix):]
            version_parts = pathlib.PurePosixPath(relative_version).parts
            if len(version_parts) != 3 or version_parts[2] != version_parts[1] + ".json":
                continue
            metadata = read_json(relative_version, 4 * 1024 * 1024)
            if not isinstance(metadata, dict):
                raise ValueError(f"Minecraft version metadata is not an object: {relative_version}.")

            # The client JAR is a required input to Horizon's native preparation.
            # Validate it against Mojang's per-version size and SHA-1 metadata so
            # a metadata-only or substituted client archive cannot pass preflight.
            downloads = metadata.get("downloads")
            client = downloads.get("client") if isinstance(downloads, dict) else None
            client_sha1 = client.get("sha1") if isinstance(client, dict) else None
            client_size = client.get("size") if isinstance(client, dict) else None
            if (not isinstance(client_sha1, str) or len(client_sha1) != 40
                    or any(c not in "0123456789abcdefABCDEF" for c in client_sha1)
                    or not isinstance(client_size, int) or client_size <= 0):
                raise ValueError(
                    f"Minecraft version metadata has invalid client JAR metadata: {relative_version}."
                )
            version_id = version_parts[1]
            client_path = f"versions/{version_id}/{version_id}.jar"
            client_info = entries.get(prefix + client_path)
            if client_info is None or client_info.file_size != client_size:
                raise ValueError(
                    f"Minecraft ZIP is missing the correctly sized client JAR: {client_path}."
                )
            client_hash = hashlib.sha1()
            with archive.open(client_info) as client_file:
                for chunk in iter(lambda: client_file.read(1024 * 1024), b""):
                    client_hash.update(chunk)
            if client_hash.hexdigest() != client_sha1.lower():
                raise ValueError(
                    f"Minecraft client JAR has a SHA-1 mismatch: {client_path} "
                    f"(expected {client_sha1.lower()}, got {client_hash.hexdigest()})."
                )

            asset_index = metadata.get("assetIndex")
            index_id = asset_index.get("id") if isinstance(asset_index, dict) else None
            if (not isinstance(index_id, str) or not index_id
                    or "/" in index_id or "\\" in index_id or index_id in {".", ".."}):
                raise ValueError(f"Minecraft version metadata has an invalid asset index id: {relative_version}.")
            index_path = f"assets/indexes/{index_id}.json"
            if prefix + index_path not in entries:
                raise ValueError(
                    f"Minecraft version metadata references a missing asset index: {index_path}."
                )
            matching_indexes.add(index_path)
        if not matching_indexes:
            raise ValueError(
                "Minecraft version metadata does not reference an included assets/indexes/<id>.json file."
            )

        # A ZIP may contain several game versions. Validate every distinct index they reference,
        # not just the first one, or an incomplete secondary version could pass preparation.
        for index_path in sorted(matching_indexes):
            index = read_json(index_path, 32 * 1024 * 1024)
            objects = index.get("objects") if isinstance(index, dict) else None
            if not isinstance(objects, dict) or not objects:
                raise ValueError(f"Minecraft asset index has no asset objects: {index_path}.")
            missing_objects = []
            for logical_name, record in objects.items():
                sha1 = record.get("hash") if isinstance(record, dict) else None
                if not isinstance(sha1, str) or len(sha1) != 40 or any(c not in "0123456789abcdefABCDEF" for c in sha1):
                    raise ValueError(f"Minecraft asset index contains an invalid SHA-1 for {logical_name}.")
                object_path = f"assets/objects/{sha1[:2].lower()}/{sha1.lower()}"
                info = entries.get(prefix + object_path)
                if info is None or info.file_size <= 0:
                    missing_objects.append(object_path)
                    if len(missing_objects) == 5:
                        break
                    continue
                # Mojang's asset index pins each object by SHA-1. Presence alone
                # is insufficient: a truncated or substituted file must fail
                # before extraction/preparation. Stream large assets to bound RAM.
                actual_hash = hashlib.sha1()
                with archive.open(info) as asset_file:
                    for chunk in iter(lambda: asset_file.read(1024 * 1024), b""):
                        actual_hash.update(chunk)
                if actual_hash.hexdigest() != sha1.lower():
                    raise ValueError(
                        f"Minecraft asset object has a SHA-1 mismatch: {object_path} "
                        f"(expected {sha1.lower()}, got {actual_hash.hexdigest()})."
                    )
            if missing_objects:
                raise ValueError(
                    f"Minecraft ZIP is missing asset objects referenced by {index_path}: "
                    + ", ".join(missing_objects)
                )

        if not any(
            name.startswith(prefix + "libraries/") and name.lower().endswith(".jar")
            and info.file_size > 0
            for name, info in entries.items()
        ):
            raise ValueError("Minecraft ZIP has no non-empty library JAR under libraries/.")

    return root

def validate_zip(path):
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Not a ZIP archive: {path}")
    with zipfile.ZipFile(path) as z:
        entries = z.infolist()
        if not entries:
            raise ValueError(f"Empty ZIP archive: {path}")
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise ValueError(
                f"ZIP archive has too many entries: {len(entries)} "
                f"(limit {MAX_ARCHIVE_ENTRIES})"
            )
        total_uncompressed = 0
        for item in entries:
            if item.flag_bits & 0x1:
                raise ValueError(f"Encrypted ZIP entry refused: {item.filename}")
            if item.is_dir():
                continue
            if item.file_size < 0 or item.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                raise ValueError(
                    f"ZIP member exceeds the uncompressed size limit: {item.filename}"
                )
            total_uncompressed += item.file_size
            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise ValueError(
                    "ZIP archive exceeds the total uncompressed size limit "
                    f"({MAX_TOTAL_UNCOMPRESSED_BYTES} bytes)"
                )
        names = []
        seen = set()
        seen_casefold = set()
        files = set()
        files_casefold = set()
        prefix_spellings = {}
        for item in entries:
            raw_name = item.filename.replace(chr(92), "/")
            parts = pathlib.PurePosixPath(raw_name).parts
            if (not parts or raw_name.startswith("/") or chr(0) in raw_name
                    or ".." in parts or any(not _portable_windows_component(part) for part in parts)):
                raise ValueError(f"Unsafe ZIP path: {item.filename}")
            name = "/".join(parts)
            if name in seen:
                raise ValueError(f"Duplicate ZIP path after normalization: {item.filename}")
            folded = _collision_key(name)
            if folded in seen_casefold:
                raise ValueError(
                    f"Case-insensitive ZIP path collision: {item.filename}"
                )
            # A ZIP may be path-safe yet impossible to extract: a regular file cannot
            # also be a parent directory (for example, "game/mods" and
            # "game/mods/example.jar"). Reject this before creating any files.
            parents = ["/".join(parts[:index]) for index in range(1, len(parts))]
            folded_parents = [_collision_key(parent) for parent in parents]
            conflicting_parent = next(
                (parent for parent in folded_parents if parent in files_casefold), None
            )
            if conflicting_parent is not None:
                raise ValueError(
                    f"ZIP file/directory path collision: {item.filename} is below file {conflicting_parent}"
                )
            is_directory = item.is_dir() or raw_name.endswith("/")
            # Directory prefixes must keep one exact spelling across the archive. Otherwise
            # Windows may merge paths that Linux/macOS extract into separate directories.
            prefix_count = len(parts) if is_directory else len(parts) - 1
            for index in range(1, prefix_count + 1):
                prefix = "/".join(parts[:index])
                folded_prefix = _collision_key(prefix)
                previous_prefix = prefix_spellings.get(folded_prefix)
                if previous_prefix is not None and previous_prefix != prefix:
                    raise ValueError(
                        f"Case-insensitive ZIP directory prefix collision: {item.filename}"
                    )
                prefix_spellings[folded_prefix] = prefix
            if not is_directory and any(
                existing.startswith(folded + "/") for existing in seen_casefold
            ):
                raise ValueError(
                    f"ZIP file/directory path collision: {item.filename} replaces a directory"
                )
            seen.add(name)
            seen_casefold.add(folded)
            if not is_directory:
                files.add(name)
                files_casefold.add(folded)
            mode = (item.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError(f"Symlink entry refused: {item.filename}")
            if mode not in (0, 0o100000, 0o040000):
                raise ValueError(f"Unsupported special ZIP entry refused: {item.filename}")
            if mode == 0o040000 and not is_directory:
                raise ValueError(f"ZIP directory mode/name mismatch: {item.filename}")
            if mode == 0o100000 and is_directory:
                raise ValueError(f"ZIP file mode/name mismatch: {item.filename}")
            names.append(name)
        return len(entries), names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", default=str(DEFAULT_INSTANCE))
    ap.add_argument("--minecraft", help="Optional full Minecraft game-directory ZIP")
    ap.add_argument("--mods", default=str(DEFAULT_MODS))
    args = ap.parse_args()
    instance = pathlib.Path(args.instance)
    mods_dir = pathlib.Path(args.mods)
    if not instance.is_file():
        raise SystemExit(f"Missing Horizon instance ZIP: {instance}")
    count, _ = validate_zip(instance)
    mods = sorted(p for p in mods_dir.glob("*.hnmod") if p.is_file())
    if not mods:
        raise SystemExit(f"No .hnmod files found in {mods_dir}")
    records = []
    for mod in mods:
        _, mod_names = validate_zip(mod)
        if not any(n.endswith("horizon-native.json") for n in mod_names):
            raise SystemExit(f"{mod.name}: missing horizon-native.json")
        if not any(n.endswith("horizon-mixin.toml") for n in mod_names):
            raise SystemExit(f"{mod.name}: missing horizon-mixin.toml")
        records.append({
            "file": mod.name,
            "bytes": mod.stat().st_size,
            "sha256": digest(mod),
        })
    manifest = {
        "schema": 3,
        "instance": {
            "file": instance.name,
            "bytes": instance.stat().st_size,
            "sha256": digest(instance),
            "zip_entries": count,
            "preserved_unchanged": True,
        },
        "mods": records,
    }
    if args.minecraft:
        minecraft = pathlib.Path(args.minecraft)
        if not minecraft.is_file():
            raise SystemExit(f"Missing Minecraft game ZIP: {minecraft}")
        try:
            minecraft_count, minecraft_names = validate_zip(minecraft)
            minecraft_root = validate_minecraft_archive(minecraft, minecraft_names)
        except ValueError as error:
            sample = chr(10).join(minecraft_names[:40]) if "minecraft_names" in locals() else ""
            raise SystemExit(
                f"{error}{chr(10)}First Minecraft ZIP entries:{chr(10)}{sample}"
            )
        manifest["minecraft"] = {
            "file": minecraft.name,
            "bytes": minecraft.stat().st_size,
            "sha256": digest(minecraft),
            "zip_entries": minecraft_count,
            "minecraft_root": minecraft_root,
        }
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "input-manifest.json").write_text(
        json.dumps(manifest, indent=2) + chr(10), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()