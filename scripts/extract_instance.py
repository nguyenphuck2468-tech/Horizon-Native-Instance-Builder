#!/usr/bin/env python3
"""Safely unpack a Minecraft game folder from the supplied instance ZIP."""
import argparse
import pathlib
import zipfile

def find_minecraft_root(root: pathlib.Path) -> pathlib.Path:
    candidates = set()
    for metadata in root.rglob("*.json"):
        if metadata.parent.parent.name == "versions" and metadata.stem == metadata.parent.name:
            candidates.add(metadata.parent.parent.parent)
    if not candidates:
        raise SystemExit(
            "The instance ZIP does not contain a Minecraft versions/<id>/<id>.json tree. "
            "Export a complete game directory (with its versions folder), not only a modpack manifest."
        )
    ranked = sorted(candidates, key=lambda p: (len(list((p / "versions").glob("*/*.json"))), str(p)), reverse=True)
    if len(ranked) > 1:
        top_count = len(list((ranked[0] / "versions").glob("*/*.json")))
        second_count = len(list((ranked[1] / "versions").glob("*/*.json")))
        if top_count == second_count:
            raise SystemExit("The ZIP contains multiple equally plausible Minecraft roots; export one instance per ZIP.")
    return ranked[0]

def extract_safe(archive: pathlib.Path, destination: pathlib.Path) -> pathlib.Path:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    seen = set()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            raw_name = info.filename.replace(chr(92), "/")
            path = pathlib.PurePosixPath(raw_name)
            if (not path.parts or raw_name.startswith("/") or chr(0) in raw_name or
                ".." in path.parts or (path.parts and ":" in path.parts[0])):
                raise SystemExit(f"Unsafe ZIP path: {info.filename}")
            normalized = "/".join(path.parts)
            if normalized in seen:
                raise SystemExit(f"Duplicate ZIP path after normalization: {info.filename}")
            seen.add(normalized)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise SystemExit(f"Symlink entry refused: {info.filename}")
            target = root.joinpath(*path.parts)
            if not target.resolve().is_relative_to(root):
                raise SystemExit(f"ZIP entry escapes extraction directory: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
    return find_minecraft_root(root)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=pathlib.Path)
    parser.add_argument("--destination", type=pathlib.Path, required=True)
    parser.add_argument("--print-root", action="store_true")
    args = parser.parse_args()
    game_root = extract_safe(args.archive, args.destination)
    if args.print_root:
        print(game_root)
    else:
        print(f"Minecraft game files found at: {game_root}")

if __name__ == "__main__":
    main()
