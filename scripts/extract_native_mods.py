#!/usr/bin/env python3
"""Safely unpack .hnmod ZIP bundles into the directory layout Horizon expects."""
import argparse
import json
import pathlib
import re
import shutil
import tempfile
import zipfile

from scripts.prepare import validate_zip


def extract_bundle(archive_path: pathlib.Path, destination: pathlib.Path) -> pathlib.Path:
    _, names = validate_zip(archive_path)
    native = [name for name in names if pathlib.PurePosixPath(name).name == "horizon-native.json"]
    mixins = [name for name in names if pathlib.PurePosixPath(name).name == "horizon-mixin.toml"]
    if len(native) != 1 or len(mixins) != 1:
        raise ValueError(
            f"{archive_path.name}: expected exactly one horizon-native.json and one "
            "horizon-mixin.toml; validate the .hnmod bundle layout"
        )

    native_path = pathlib.PurePosixPath(native[0])
    root_prefix = native_path.parent.as_posix()
    root_prefix = "" if root_prefix == "." else root_prefix + "/"
    try:
        with zipfile.ZipFile(archive_path) as bundle:
            raw_manifest = bundle.read(native[0])
            manifest = json.loads(raw_manifest)
            mod_id = manifest.get("id")
            if not isinstance(mod_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", mod_id):
                raise ValueError(f"{archive_path.name}: invalid or missing native mod id")
            expected_mixin = root_prefix + f"mixins/{mod_id}/horizon-mixin.toml"
            if expected_mixin not in mixins:
                raise ValueError(
                    f"{archive_path.name}: expected {expected_mixin} to match native mod id {mod_id!r}"
                )

            destination.mkdir(parents=True, exist_ok=True)
            target = destination / archive_path.stem
            if target.exists():
                shutil.rmtree(target)
            with tempfile.TemporaryDirectory(prefix="hnmod-") as temp:
                staging = pathlib.Path(temp)
                for name in names:
                    if root_prefix and not name.startswith(root_prefix):
                        continue
                    relative = name[len(root_prefix):] if root_prefix else name
                    if not relative or relative.endswith("/"):
                        continue
                    rel = pathlib.PurePosixPath(relative)
                    if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
                        raise ValueError(f"{archive_path.name}: unsafe bundle path {relative!r}")
                    output = staging.joinpath(*rel.parts)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(name) as source, output.open("wb") as sink:
                        shutil.copyfileobj(source, sink, length=1024 * 1024)
                if not (staging / "horizon-native.json").is_file():
                    raise ValueError(f"{archive_path.name}: native manifest was not extracted at bundle root")
                if not (staging / f"mixins/{mod_id}/horizon-mixin.toml").is_file():
                    raise ValueError(f"{archive_path.name}: mixin manifest was not extracted")
                shutil.move(str(staging), str(target))
            return target
    except (zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError(f"{archive_path.name}: invalid native mod archive: {error}") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=pathlib.Path, nargs="?", default=pathlib.Path("input/mods"))
    parser.add_argument("--destination", type=pathlib.Path, default=pathlib.Path("input/mods-unpacked"))
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    archives = sorted(args.source.glob("*.hnmod")) if args.source.is_dir() else []
    if not archives:
        print("No .hnmod bundles supplied; Core Build will produce the unmodified Horizon client.")
        return
    extracted = [extract_bundle(path, args.destination) for path in archives]
    print(f"Extracted {len(extracted)} native mod bundle(s): " + ", ".join(p.name for p in extracted))


if __name__ == "__main__":
    main()
