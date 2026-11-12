#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INSTANCE = ROOT / "input/instance/instance.zip"
DEFAULT_MINECRAFT = ROOT / "input/minecraft/minecraft.zip"
DEFAULT_MODS = ROOT / "input/mods"
REPORT = ROOT / "build-report"


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
    root = validate_minecraft_layout(names)
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
        matching_indexes = []
        for version_file in version_files:
            metadata = read_json(version_file[len(prefix):], 4 * 1024 * 1024)
            asset_index = metadata.get("assetIndex") if isinstance(metadata, dict) else None
            index_id = asset_index.get("id") if isinstance(asset_index, dict) else None
            if isinstance(index_id, str) and index_id and "/" not in index_id and "\\\\" not in index_id:
                index_path = f"assets/indexes/{index_id}.json"
                if prefix + index_path in entries:
                    matching_indexes.append(index_path)
        if not matching_indexes:
            raise ValueError(
                "Minecraft version metadata does not reference an included assets/indexes/<id>.json file."
            )

        index = read_json(matching_indexes[0], 32 * 1024 * 1024)
        objects = index.get("objects") if isinstance(index, dict) else None
        if not isinstance(objects, dict) or not objects:
            raise ValueError("Minecraft asset index has no asset objects.")
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
        if missing_objects:
            raise ValueError(
                "Minecraft ZIP is missing asset objects referenced by its index: "
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
        names = []
        seen = set()
        for item in entries:
            raw_name = item.filename.replace(chr(92), "/")
            parts = pathlib.PurePosixPath(raw_name).parts
            if (not parts or raw_name.startswith("/") or chr(0) in raw_name
                    or ".." in parts or (parts and ":" in parts[0])):
                raise ValueError(f"Unsafe ZIP path: {item.filename}")
            name = "/".join(parts)
            if name in seen:
                raise ValueError(f"Duplicate ZIP path after normalization: {item.filename}")
            seen.add(name)
            mode = (item.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError(f"Symlink entry refused: {item.filename}")
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
