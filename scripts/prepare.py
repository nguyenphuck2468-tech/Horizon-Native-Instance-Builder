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
            minecraft_root = discover_minecraft_root(minecraft_names)
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
