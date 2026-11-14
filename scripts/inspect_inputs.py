#!/usr/bin/env python3
"""Inspect the supplied Horizon instance and every .hnmod without modifying inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import tomllib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_mod(path: pathlib.Path) -> dict:
    result = {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"{path.name}: corrupt member {bad}")
        names = archive.namelist()
        manifest_names = [n for n in names if pathlib.PurePosixPath(n).name == "horizon-native.json"]
        mixin_names = [n for n in names if pathlib.PurePosixPath(n).name == "horizon-mixin.toml"]
        if len(manifest_names) != 1 or len(mixin_names) != 1:
            raise ValueError(f"{path.name}: expected one manifest and one mixin config")
        manifest = json.loads(archive.read(manifest_names[0]))
        mixin_raw = archive.read(mixin_names[0]).decode("utf-8")
        mixin = tomllib.loads(mixin_raw)
        source_files = {}
        for name in names:
            if name.endswith(".rs"):
                source_files[name] = archive.read(name).decode("utf-8", errors="replace")
        interesting = {}
        for name, content in source_files.items():
            lines = content.splitlines()
            matches = [i for i, line in enumerate(lines) if re.search(
                r"\b(Button|action|title\.rs|struct\s+|impl\s+|fn\s+)", line, re.I
            )]
            if matches:
                spans = []
                used = set()
                for index in matches:
                    for pos in range(max(0, index - 3), min(len(lines), index + 5)):
                        if pos not in used:
                            spans.append(f"{pos + 1}: {lines[pos]}")
                            used.add(pos)
                interesting[name] = "\n".join(spans)
        result.update({
            "manifest": manifest,
            "mixin": mixin,
            "source_files": {name: {"bytes": len(content.encode()), "sha256": hashlib.sha256(content.encode()).hexdigest()}
                             for name, content in source_files.items()},
            "source_context": interesting,
            "archive_members": [{"name": n, "bytes": archive.getinfo(n).file_size}
                                for n in names if not n.endswith("/")],
        })
    return result


def inspect_instance(path: pathlib.Path) -> dict:
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Invalid instance archive: {path}")
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Instance ZIP CRC failure: {bad}")
        names = archive.namelist()
        roots = sorted({pathlib.PurePosixPath(n).parts[0] for n in names if pathlib.PurePosixPath(n).parts})
        candidates = []
        for name in names:
            p = pathlib.PurePosixPath(name)
            if len(p.parts) >= 3 and p.parts[-1].endswith(".json") and p.parts[-3] == "versions":
                candidates.append(name)
        return {
            "file": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "entry_count": len(names),
            "top_level_entries": roots,
            "minecraft_version_metadata": candidates[:100],
            "selected_entries": [
                {"name": n, "bytes": archive.getinfo(n).file_size}
                for n in names
                if any(token in n.lower() for token in (
                    "instance.json", "profile.json", "launcher_profiles.json",
                    "versions/", "mods/", "config/", "resourcepacks/",
                    "shaderpacks/", "options.txt", "servers.dat", "saves/"
                ))
            ][:500],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=pathlib.Path, default=ROOT / "input/instance/instance.zip")
    parser.add_argument("--mods", type=pathlib.Path, default=ROOT / "input/mods")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "build-report/input-inspection.json")
    args = parser.parse_args()
    mods = sorted(args.mods.glob("*.hnmod"))
    report = {
        "schema": 1,
        "read_only": True,
        "instance": inspect_instance(args.instance),
        "mods": [read_mod(path) for path in mods],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "instance_sha256": report["instance"]["sha256"],
        "instance_entries": report["instance"]["entry_count"],
        "instance_top_level": report["instance"]["top_level_entries"],
        "mod_count": len(mods),
        "mods": [{
            "file": mod["file"],
            "id": mod["manifest"].get("id"),
            "version": mod["manifest"].get("version"),
            "horizon_version": mod["manifest"].get("horizon_version"),
            "horizon_commit": mod["manifest"].get("horizon_commit"),
            "source_files": list(mod["source_files"]),
        } for mod in report["mods"]],
        "report": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
