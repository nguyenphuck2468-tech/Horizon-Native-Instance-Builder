#!/usr/bin/env python3
"""Verify that both native artifacts match the single validated Horizon revision."""
import argparse
import hashlib
import json
import re
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        size = binary.stat().st_size
        if size <= 0:
            raise ValueError(f"{target}: native client binary is empty: {binary}")
        verified[target] = {
            "client": client_name,
            "bytes": size,
            "sha256": _sha256(binary),
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
