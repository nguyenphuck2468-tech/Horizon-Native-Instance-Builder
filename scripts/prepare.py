#!/usr/bin/env python3
import argparse, hashlib, json, pathlib, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INSTANCE = ROOT / "input/instance/instance.zip"
DEFAULT_MODS = ROOT / "input/mods"
REPORT = ROOT / "build-report"

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def validate_zip(path):
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Not a ZIP archive: {path}")
    with zipfile.ZipFile(path) as z:
        entries = z.infolist()
        if not entries:
            raise ValueError(f"Empty ZIP archive: {path}")
        for item in entries:
            name = item.filename.replace("\\\\", "/")
            parts = pathlib.PurePosixPath(name).parts
            if name.startswith("/") or ".." in parts:
                raise ValueError(f"Unsafe ZIP path: {item.filename}")
            mode = (item.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError(f"Symlink entry refused: {item.filename}")
        return len(entries), [x.filename for x in entries]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", default=str(DEFAULT_INSTANCE))
    ap.add_argument("--mods", default=str(DEFAULT_MODS))
    args = ap.parse_args()
    instance = pathlib.Path(args.instance)
    mods_dir = pathlib.Path(args.mods)
    if not instance.is_file():
        raise SystemExit(f"Missing instance ZIP: {instance}")
    count, names = validate_zip(instance)
    mods = sorted(p for p in mods_dir.glob("*.hnmod") if p.is_file())
    if not mods:
        raise SystemExit(f"No .hnmod files found in {mods_dir}")
    records = []
    for mod in mods:
        _, mod_names = validate_zip(mod)
        if not any(n.endswith("horizon-native.json") for n in mod_names):
            raise SystemExit(f"{mod.name}: missing horizon-native.json")
        if not any(n.endswith("horizon-mixin.toml") for n in mod_names):
            raise SystemExit(f"{mod.name}: missing horizon-mixin.toml")
        records.append({"file": mod.name, "bytes": mod.stat().st_size, "sha256": digest(mod)})
    REPORT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": 1,
        "instance": {"file": instance.name, "bytes": instance.stat().st_size,
                     "sha256": digest(instance), "zip_entries": count},
        "mods": records,
        "instance_zip_is_preserved_unchanged": True
    }
    (REPORT / "input-manifest.json").write_text(json.dumps(manifest, indent=2) + "\\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
