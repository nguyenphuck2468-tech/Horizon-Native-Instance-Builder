#!/usr/bin/env python3
"""Verify that both native artifacts match the single validated Horizon revision."""
import argparse
import hashlib
import json
import os
import re
import stat
import struct
from pathlib import Path


_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _report(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"missing build report: {path}")
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        if key in fields:
            raise ValueError(f"duplicate build report field {key!r}: {path}")
        fields[key] = value
    return fields


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _is_reparse_point(metadata: os.stat_result) -> bool:
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_attribute
    )


def _inspect_binary(path: Path, target: str) -> tuple[int, str]:
    """Validate the executable header and hash the same stable, regular file handle."""
    try:
        path_before = path.lstat()
    except OSError as error:
        raise ValueError(f"{target}: cannot inspect native client: {error}") from error
    if _is_reparse_point(path_before):
        raise ValueError(f"{target}: refusing symlink or reparse-point native client")

    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or _is_reparse_point(before):
            raise ValueError(f"{target}: native client is not a regular file")
        # Compare path metadata with path metadata and handle metadata with handle
        # metadata separately: Windows may expose different file IDs for lstat/fstat.
        if not stat.S_ISREG(path_before.st_mode) or path_before.st_size != before.st_size:
            raise ValueError(f"{target}: native client changed before verification")
        size = before.st_size
        if size <= 0:
            raise ValueError(f"{target}: native client binary is empty")

        if target == "linux-x86_64":
            header = stream.read(20)
            if len(header) < 20 or header[:4] != b"\x7fELF":
                raise ValueError(f"{target}: native client is not an ELF executable")
            if header[4] != 2 or header[5] != 1:
                raise ValueError(f"{target}: expected a 64-bit little-endian ELF executable")
            machine = struct.unpack_from("<H", header, 18)[0]
            if machine != 62:
                raise ValueError(f"{target}: expected ELF x86_64 machine (62), got {machine}")
        elif target == "windows-x86_64":
            dos_header = stream.read(64)
            if len(dos_header) < 64 or dos_header[:2] != b"MZ":
                raise ValueError(f"{target}: native client is not a PE executable")
            pe_offset = struct.unpack_from("<I", dos_header, 0x3C)[0]
            if pe_offset < 64 or pe_offset + 6 > size:
                raise ValueError(f"{target}: invalid or truncated PE header offset")
            stream.seek(pe_offset)
            pe_header = stream.read(6)
            if len(pe_header) != 6 or pe_header[:4] != b"PE\x00\x00":
                raise ValueError(f"{target}: invalid PE signature")
            machine = struct.unpack_from("<H", pe_header, 4)[0]
            if machine != 0x8664:
                raise ValueError(
                    f"{target}: expected PE AMD64 machine (0x8664), got 0x{machine:04x}"
                )
        else:
            raise ValueError(f"unsupported native artifact target: {target}")

        stream.seek(0)
        digest = hashlib.sha256()
        bytes_read = 0
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            bytes_read += len(chunk)
            digest.update(chunk)

        after = os.fstat(stream.fileno())
        try:
            path_after = path.lstat()
        except OSError as error:
            raise ValueError(f"{target}: native client path changed during verification") from error
        if (
            _file_identity(before) != _file_identity(after)
            or _file_identity(path_before) != _file_identity(path_after)
            or _is_reparse_point(path_after)
            or bytes_read != size
        ):
            raise ValueError(f"{target}: native client changed during verification")

    return size, digest.hexdigest()


def verify_artifacts(inputs: Path, linux: Path, windows: Path) -> dict:
    pinned_path = inputs / "build-report" / "horizon-commit.txt"
    if not pinned_path.is_file():
        raise ValueError(f"missing validated Horizon commit: {pinned_path}")
    pinned_commit = pinned_path.read_text(encoding="ascii").strip().lower()
    if not _COMMIT_RE.fullmatch(pinned_commit):
        raise ValueError("validated Horizon commit must be a full 40-character SHA-1")

    targets = (
        ("linux-x86_64", linux, "horizon-client"),
        ("windows-x86_64", windows, "horizon-client.exe"),
    )
    verified = {}
    for target, root, client_name in targets:
        report_path = root / "build-report" / target / "build.txt"
        fields = _report(report_path)
        if fields.get("Target") != target:
            raise ValueError(f"{target}: build report target mismatch")
        actual_commit = fields.get("Horizon commit", "").lower()
        if actual_commit != pinned_commit:
            raise ValueError(
                f"{target}: Horizon commit mismatch; expected {pinned_commit}, got {actual_commit or '<missing>'}"
            )
        binary = root / "native-runtime" / client_name
        if not binary.is_file():
            raise ValueError(f"{target}: missing native client binary: {binary}")
        size, digest = _inspect_binary(binary, target)
        verified[target] = {
            "client": client_name,
            "bytes": size,
            "sha256": digest,
            "horizon_commit": actual_commit,
        }

    return {
        "schema": 1,
        "status": "VERIFIED",
        "horizon_commit": pinned_commit,
        "targets": verified,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--linux", type=Path, required=True)
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify_artifacts(args.inputs, args.linux, args.windows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Verified Linux and Windows native artifacts from Horizon "
        f"{result['horizon_commit']}."
    )


if __name__ == "__main__":
    main()
