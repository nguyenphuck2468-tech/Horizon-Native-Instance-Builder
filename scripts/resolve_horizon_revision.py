#!/usr/bin/env python3
"""Resolve the immutable source commit behind Horizon's current official Nightly."""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

API = "https://api.github.com/repos/horizon-rust/horizon/releases/tags/nightly"
SHA = re.compile(r"^[0-9a-f]{40}$")


def fetch_release() -> dict:
    request = urllib.request.Request(
        API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "horizon-native-instance-builder",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        value = json.loads(response.read())
    if value.get("tag_name") != "nightly" or not value.get("prerelease"):
        raise ValueError("GitHub did not return the current Horizon Nightly release.")
    commit = value.get("target_commitish", "")
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        body = value.get("body", "")
        match = re.search(r"Source: commit ([0-9a-f]{40})", body)
        commit = match.group(1) if match else ""
    if not SHA.fullmatch(commit):
        raise ValueError("The Nightly release does not identify an immutable 40-character commit.")
    return {
        "tag": value["tag_name"],
        "name": value.get("name", ""),
        "published_at": value.get("published_at", ""),
        "commit": commit,
        "url": value.get("html_url", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    release = fetch_release()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(release["commit"] + "\n", encoding="ascii")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Resolved {release['name']} to {release['commit']}")


if __name__ == "__main__":
    main()
