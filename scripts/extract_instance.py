#!/usr/bin/env python3
"""Safely unpack a Minecraft game folder from the supplied instance ZIP."""
import argparse
import pathlib
import stat
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



def _metadata_is_link_or_reparse_point(metadata):
    """Recognize POSIX symlinks and Windows reparse points (including junctions)."""
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & 0x400
    )


def _is_link_or_reparse_point(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return _metadata_is_link_or_reparse_point(metadata)


def _collision_key(value):
    """Normalize canonical Unicode equivalents before case-insensitive comparison."""
    normalized = unicodedata.normalize("NFC", value)
    return unicodedata.normalize("NFC", normalized.casefold())


def find_minecraft_root(root: pathlib.Path, archive_files=None) -> pathlib.Path:
    # When extracting into an existing destination, never let an older Minecraft tree
    # satisfy validation for a new archive that contains no version metadata.
    if archive_files is not None:
        version_counts = {}
        for name in archive_files:
            parts = pathlib.PurePosixPath(name).parts
            if (
                len(parts) >= 3
                and parts[-3] == "versions"
                and parts[-1] == parts[-2] + ".json"
            ):
                relative_root = pathlib.PurePosixPath(*parts[:-3])
                version_counts[relative_root] = version_counts.get(relative_root, 0) + 1
        if not version_counts:
            raise SystemExit(
                "The instance ZIP does not contain a Minecraft versions/<id>/<id>.json tree. "
                "Export a complete game directory (with its versions folder), not only a modpack manifest."
            )
        ranked = sorted(version_counts.items(), key=lambda item: (item[1], str(item[0])), reverse=True)
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            raise SystemExit("The ZIP contains multiple equally plausible Minecraft roots; export one instance per ZIP.")
        relative_root = ranked[0][0]
        return root if str(relative_root) == "." else root.joinpath(*relative_root.parts)

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
    # Path.is_symlink() misses Windows junctions. Reject reparse points before resolve()
    # can silently redirect the caller-selected destination.
    if _is_link_or_reparse_point(destination):
        raise SystemExit(
            f"symlink extraction destination refused (including Windows reparse points): {destination}"
        )
    # Resolve without creating the destination. An invalid archive must not leave
    # even an empty output directory behind.
    root = destination.resolve()
    seen = set()
    seen_casefold = set()
    files_casefold = set()
    prefix_spellings = {}
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
            # Keep every directory prefix's spelling stable so Windows and POSIX do not
            # materialize different directory trees from the same archive.
            prefix_count = len(path.parts) if is_directory else len(path.parts) - 1
            for index in range(1, prefix_count + 1):
                prefix = "/".join(path.parts[:index])
                folded_prefix = _collision_key(prefix)
                previous_prefix = prefix_spellings.get(folded_prefix)
                if previous_prefix is not None and previous_prefix != prefix:
                    raise SystemExit(
                        f"Case-insensitive ZIP directory prefix collision: {info.filename}"
                    )
                prefix_spellings[folded_prefix] = prefix
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

        # Only create the output directory after every archive entry has passed preflight.
        destination_missing = []
        current = destination.absolute()
        while current != current.parent and not current.exists():
            destination_missing.append(current)
            current = current.parent
        destination.mkdir(parents=True, exist_ok=True)
        root = destination.resolve()

        created_files = []
        created_directories = list(reversed(destination_missing))

        def ensure_directory(path):
            missing = []
            current = path
            while current != root and not current.exists():
                missing.append(current)
                current = current.parent
            path.mkdir(parents=True, exist_ok=True)
            created_directories.extend(reversed(missing))

        try:
            for info, path, is_directory in validated_entries:
                target = root.joinpath(*path.parts)
                current = root
                for part in path.parts:
                    current = current / part
                    # Recheck every existing component immediately before writing. This
                    # includes junctions and other Windows reparse points, not just symlinks.
                    if _is_link_or_reparse_point(current):
                        raise SystemExit(
                            f"Existing symlink or reparse point in extraction path refused: {current}"
                        )
                if is_directory:
                    ensure_directory(target)
                    continue
                ensure_directory(target.parent)
                with zf.open(info) as source:
                    with target.open("xb") as output:
                        created_files.append(target)
                        while chunk := source.read(1024 * 1024):
                            output.write(chunk)

            archive_files = [path.as_posix() for _, path, is_directory in validated_entries if not is_directory]
            return find_minecraft_root(root, archive_files)
        except BaseException:
            # Extraction is exclusive: only remove files and directories created by this
            # invocation, never pre-existing destination content.
            for created in reversed(created_files):
                created.unlink(missing_ok=True)
            for created in reversed(created_directories):
                try:
                    created.rmdir()
                except OSError:
                    pass
            raise

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