#!/usr/bin/env python3
"""Check that a Minecraft archive matches the selected Horizon research lock."""
import argparse
import json
import pathlib
import zipfile

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True)
    parser.add_argument("--minecraft-zip", required=True)
    parser.add_argument("--print-version", action="store_true")
    args = parser.parse_args()
    try:
        lock = json.loads(pathlib.Path(args.lock).read_text(encoding="utf-8"))
        expected = lock.get("minecraft", {}).get("version")
        if not isinstance(expected, str) or not expected:
            raise ValueError("Selected Horizon research-lock.json has no minecraft.version.")
        with zipfile.ZipFile(args.minecraft_zip) as archive:
            found = set()
            for name in archive.namelist():
                parts = pathlib.PurePosixPath(name.replace(chr(92), "/")).parts
                if len(parts) >= 3 and parts[-3] == "versions" and parts[-1] == parts[-2] + ".json":
                    metadata = json.loads(archive.read(name))
                    if isinstance(metadata, dict) and isinstance(metadata.get("id"), str):
                        found.add(metadata["id"])
        if expected not in found:
            raise ValueError(f"Selected Horizon revision requires {expected}, but archive contains {sorted(found)}. Set minecraft_version to {expected}.")
        if args.print_version: print(expected)
        else: print(f"Minecraft {expected} matches the selected Horizon lock.")
    except (OSError, KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile, ValueError) as error:
        raise SystemExit(f"Horizon/Minecraft compatibility check failed: {error}") from error

if __name__ == "__main__": main()
