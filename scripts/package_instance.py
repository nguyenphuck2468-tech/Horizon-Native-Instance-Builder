#!/usr/bin/env python3
"""Build a Horizon game-home drop-in bundle with a real instances/<id> directory."""
import argparse
import hashlib
import json
import pathlib
import re
import stat
import zipfile


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_members(archive: zipfile.ZipFile):
    seen = set()
    folded = set()
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        path = pathlib.PurePosixPath(name)
        mode = (info.external_attr >> 16) & 0o170000
        if (
            not path.parts or name.startswith("/") or "\x00" in name
            or any(part in ("", ".", "..") for part in path.parts)
            or any(":" in part or part.endswith((" ", ".")) for part in path.parts)
            or mode == stat.S_IFLNK
            or info.flag_bits & 0x1
        ):
            raise ValueError(f"Unsafe instance ZIP entry: {info.filename}")
        if any(re.fullmatch(r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\\..*)?", part, re.I)
               for part in path.parts):
            raise ValueError(f"Windows-reserved instance path: {info.filename}")
        normalized = "/".join(path.parts)
        key = normalized.casefold()
        if key in folded:
            raise ValueError(f"Duplicate/case-colliding instance path: {info.filename}")
        folded.add(key)
        seen.add(normalized)
        yield info, normalized


def package(instance: pathlib.Path, binary: pathlib.Path, mods: pathlib.Path,
            target: str, horizon_commit: str, output: pathlib.Path) -> dict:
    if not instance.is_file() or not zipfile.is_zipfile(instance):
        raise ValueError(f"Missing or invalid original instance ZIP: {instance}")
    if not binary.is_file() or binary.stat().st_size == 0:
        raise ValueError(f"Missing native client binary: {binary}")
    if not re.fullmatch(r"[0-9a-f]{40}", horizon_commit):
        raise ValueError("horizon_commit must be a full 40-character commit SHA")
    instance_id = f"horizon-native-{horizon_commit[:7]}"
    mod_files = sorted(p for p in mods.glob("*.hnmod") if p.is_file())
    with zipfile.ZipFile(instance) as source:
        members = list(safe_members(source))
        if not members:
            raise ValueError("Original instance ZIP is empty")
        instance_files = [(info, name) for info, name in members if not info.is_dir()]
        if not instance_files:
            raise ValueError("Original instance ZIP contains no files")

    manifest = {
        "schema": 2,
        "package": "Horizon drop-in instance",
        "target": target,
        "horizon_commit": horizon_commit,
        "instance": {
            "id": instance_id,
            "relative_path": f"instances/{instance_id}",
            "source_archive_sha256": sha256(instance),
            "source_archive_bytes": instance.stat().st_size,
            "files": len(instance_files),
        },
        "native_client": {
            "path": f"native-build/{target}/{binary.name}",
            "sha256": sha256(binary),
            "bytes": binary.stat().st_size,
            "version": f"native-{horizon_commit[:7]}",
        },
        "mods": [{"file": p.name, "sha256": sha256(p), "bytes": p.stat().st_size}
                 for p in mod_files],
    }
    instructions = f"""Horizon drop-in instance

Target: {target}
Horizon source: {horizon_commit}
Instance folder: instances/{instance_id}

INSTALL
1. Extract this package into Horizon's GAME HOME folder (the folder that already contains
   saves/options.txt for the default Horizon instance). Do not extract it into the launcher
   program folder. The result must be GAME_HOME/instances/{instance_id}/...
2. Import the included native client using the Horizon Launcher CLI:
   horizon-launcher import-build "native-build/{target}/{binary.name}" --trust-unsigned
3. Pin and select this instance:
   horizon-launcher instance version "{instance_id}" "native-{horizon_commit[:7]}"
   horizon-launcher instance select "{instance_id}"
4. Open Horizon Launcher. The instance should appear in the instance list.

The instance's game files are now a real Horizon instances/<id> directory; no ZIP restore/import
is required. The native build is installed in Horizon's separate version store and associated
with this instance using Horizon's own CLI, because the launcher keeps versions and instance
metadata outside the instances directory.

The original instance ZIP is unpacked without changing file contents. Its archive checksum,
the native executable checksum, and mod input checksums are recorded in build-manifest.json.
Native builds execute with your user permissions. Only import builds and mods you trust.
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        with zipfile.ZipFile(instance) as source:
            for info, name in members:
                if info.is_dir():
                    continue
                archive.writestr(f"instances/{instance_id}/{name}", source.read(info))
        archive.write(binary, manifest["native_client"]["path"])
        for mod in mod_files:
            archive.write(mod, f"build-inputs/mods/{mod.name}")
        archive.writestr("build-manifest.json",
                         json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        archive.writestr("README-INSTALL.txt", instructions)
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Packaged ZIP failed CRC verification at {bad}")
        required = {
            f"instances/{instance_id}/" + instance_files[0][1],
            manifest["native_client"]["path"],
            "build-manifest.json",
            "README-INSTALL.txt",
        }
        missing = required.difference(archive.namelist())
        if missing:
            raise ValueError(f"Package is missing required entries: {sorted(missing)}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=pathlib.Path, required=True)
    parser.add_argument("--binary", type=pathlib.Path, required=True)
    parser.add_argument("--mods", type=pathlib.Path, required=True)
    parser.add_argument("--target", required=True,
                        choices=("windows-x86_64", "linux-x86_64"))
    parser.add_argument("--horizon-commit", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = package(args.instance, args.binary, args.mods, args.target,
                     args.horizon_commit, args.output)
    print(json.dumps({
        "status": "PACKAGED_DROP_IN_INSTANCE",
        "output": str(args.output),
        "target": args.target,
        "instance_id": result["instance"]["id"],
        "instance_files": result["instance"]["files"],
        "mod_count": len(result["mods"]),
        "instance_source_sha256": result["instance"]["source_archive_sha256"],
        "client_sha256": result["native_client"]["sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
