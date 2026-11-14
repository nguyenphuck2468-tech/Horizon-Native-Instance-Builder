#!/usr/bin/env python3
"""Create one downloadable bundle containing the original instance and a native client build."""
import argparse
import hashlib
import json
import pathlib
import zipfile


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package(instance: pathlib.Path, binary: pathlib.Path, mods: pathlib.Path,
            target: str, horizon_commit: str, output: pathlib.Path) -> dict:
    if not instance.is_file() or not zipfile.is_zipfile(instance):
        raise ValueError(f"Missing or invalid original instance ZIP: {instance}")
    if not binary.is_file() or binary.stat().st_size == 0:
        raise ValueError(f"Missing native client binary: {binary}")
    mod_files = sorted(p for p in mods.glob("*.hnmod") if p.is_file())
    manifest = {
        "schema": 1,
        "package": "Horizon native instance bundle",
        "target": target,
        "horizon_commit": horizon_commit,
        "instance": {"path": "instance/instance.zip", "sha256": sha256(instance),
                     "bytes": instance.stat().st_size},
        "native_client": {"path": f"native/{target}/{binary.name}",
                          "sha256": sha256(binary), "bytes": binary.stat().st_size},
        "mods": [{"file": p.name, "sha256": sha256(p), "bytes": p.stat().st_size}
                 for p in mod_files],
    }
    instructions = f"""Horizon native instance bundle

Target: {target}
Horizon source: {horizon_commit}

Contents:
- instance/instance.zip: your original Horizon instance backup, preserved byte-for-byte.
- native/{target}/{binary.name}: the native client built for this platform.
- mods/: the original .hnmod inputs used by the build.
- build-manifest.json: SHA-256 checksums and build provenance.

Install:
1. Extract this package.
2. Restore/import instance/instance.zip using Horizon's instance restore/import flow.
3. Import the native client with Horizon Launcher:
   horizon-launcher import-build "native/{target}/{binary.name}" --trust-unsigned
4. Select the imported native version for the restored instance if it is not selected automatically.

Native builds execute with your user permissions. Only import builds and mods you trust.
This bundle keeps the instance backup and platform-specific executable together; it does
not alter or overwrite the original instance ZIP.
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        archive.write(instance, "instance/instance.zip")
        archive.write(binary, f"native/{target}/{binary.name}")
        for mod in mod_files:
            archive.write(mod, f"mods/{mod.name}")
        archive.writestr("build-manifest.json",
                         json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        archive.writestr("README-INSTALL.txt", instructions)
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Packaged ZIP failed CRC verification at {bad}")
        required = {"instance/instance.zip", f"native/{target}/{binary.name}",
                    "build-manifest.json", "README-INSTALL.txt"}
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
    print(json.dumps({"status": "PACKAGED", "output": str(args.output),
                      "target": args.target, "mod_count": len(result["mods"]),
                      "instance_sha256": result["instance"]["sha256"],
                      "client_sha256": result["native_client"]["sha256"]},
                     indent=2))


if __name__ == "__main__":
    main()
