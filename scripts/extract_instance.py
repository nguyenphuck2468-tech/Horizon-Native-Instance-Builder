#!/usr/bin/env python3
"""Safely unpack a Minecraft game folder from the supplied instance ZIP."""
import argparse
import pathlib
import unicodedata
import zipfile

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
    seen_casefold = set()
    files_casefold = set()
    validated_entries = []

    # Validate the complete archive before writing anything. This prevents a late malicious
    # entry from leaving a partially extracted tree behind.
    with zipfile.ZipFile(archive) as zf:
        entries = zf.infolist()
        if not entries:
            raise SystemExit("Empty ZIP archive")
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise SystemExit(
                f"ZIP archive has too many entries: {len(entries)} "
                f"(limit {MAX_ARCHIVE_ENTRIES})"
            )
        total_uncompressed = 0
        for info in entries:
            raw_name = info.filename.replace(chr(92), "/")
            is_directory = info.is_dir() or raw_name.endswith("/")
            if info.flag_bits & 0x1:
                raise SystemExit(f"Encrypted ZIP entry refused: {info.filename}")
            if not is_directory:
                if info.file_size < 0 or info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                    raise SystemExit(
                        f"ZIP member exceeds the uncompressed size limit: {info.filename}"
                    )
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise SystemExit(
                        "ZIP archive exceeds the total uncompressed size limit "
                        f"({MAX_TOTAL_UNCOMPRESSED_BYTES} bytes)"
                    )
            path = pathlib.PurePosixPath(raw_name)
            if (
                not path.parts
                or raw_name.startswith("/")
                or chr(0) in raw_name
                or ".." in path.parts
                or any(not _portable_windows_component(part) for part in path.parts)
            ):
                raise SystemExit(f"Unsafe ZIP path: {info.filename}")
            normalized = "/".join(path.parts)
            if normalized in seen:
                raise SystemExit(f"Duplicate ZIP path after normalization: {info.filename}")
            folded = _collision_key(normalized)
            if folded in seen_casefold:
                raise SystemExit(f"Case-insensitive ZIP path collision: {info.filename}")
            parents = ["/".join(path.parts[:index]) for index in range(1, len(path.parts))]
            conflicting_parent = next(
                (_collision_key(parent) for parent in parents if _collision_key(parent) in files_casefold),
                None,
            )
            if conflicting_parent is not None:
                raise SystemExit(
                    f"ZIP file/directory path collision: {info.filename} is below file {conflicting_parent}"
                )
            if not is_directory and any(
                existing.startswith(folded + "/") for existing in seen_casefold
            ):
                raise SystemExit(
                    f"ZIP file/directory path collision: {info.filename} replaces a directory"
                )
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise SystemExit(f"Symlink entry refused: {info.filename}")
            if mode not in (0, 0o100000, 0o040000):
                raise SystemExit(f"Unsupported special ZIP entry refused: {info.filename}")
            if mode == 0o040000 and not is_directory:
                raise SystemExit(f"ZIP directory mode/name mismatch: {info.filename}")
            if mode == 0o100000 and is_directory:
                raise SystemExit(f"ZIP file mode/name mismatch: {info.filename}")
            target = root.joinpath(*path.parts)
            if not target.resolve().is_relative_to(root):
                raise SystemExit(f"ZIP entry escapes extraction directory: {info.filename}")
            seen.add(normalized)
            seen_casefold.add(folded)
            if not is_directory:
                files_casefold.add(folded)
            validated_entries.append((info, path, is_directory))

        for info, path, is_directory in validated_entries:
            target = root.joinpath(*path.parts)
            current = root
            for part in path.parts:
                current = current / part
                if current.is_symlink():
                    raise SystemExit(
                        f"Existing symlink in extraction path refused: {current}"
                    )
            if is_directory:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, target.open("xb") as output:
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