import json
import pathlib
import tempfile
import unittest
import zipfile

from scripts.extract_native_mods import extract_bundle


class NativeModExtractionTests(unittest.TestCase):
    def _bundle(self, path, root=""):
        prefix = root + "/" if root else ""
        manifest = {"id": "sample_mod", "horizon": "test"}
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(prefix + "horizon-native.json", json.dumps(manifest))
            archive.writestr(
                prefix + "mixins/sample_mod/horizon-mixin.toml",
                '[mod]\nid = "sample_mod"\nversion = "1.0.0"\n',
            )
            archive.writestr(prefix + "mixins/sample_mod/src/lib.rs", "pub fn hook() {}\n")

    def test_extracts_root_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "sample.hnmod"
            self._bundle(archive)
            result = extract_bundle(archive, root / "out")
            self.assertTrue((result / "horizon-native.json").is_file())
            self.assertTrue((result / "mixins/sample_mod/horizon-mixin.toml").is_file())

    def test_strips_single_bundle_directory_prefix(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "sample.hnmod"
            self._bundle(archive, "sample")
            result = extract_bundle(archive, root / "out")
            self.assertTrue((result / "horizon-native.json").is_file())

    def test_rejects_mismatched_manifest_id_and_mixin_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "sample.hnmod"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("horizon-native.json", '{"id":"sample_mod"}')
                bundle.writestr("mixins/other/horizon-mixin.toml", '[mod]')
            with self.assertRaisesRegex(ValueError, "expected mixins/sample_mod"):
                extract_bundle(archive, root / "out")

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "sample.hnmod"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../outside.txt", "no")
                bundle.writestr("horizon-native.json", '{"id":"sample_mod"}')
                bundle.writestr("mixins/sample_mod/horizon-mixin.toml", '[mod]')
            with self.assertRaisesRegex(ValueError, "Unsafe ZIP path"):
                extract_bundle(archive, root / "out")


if __name__ == "__main__":
    unittest.main()
