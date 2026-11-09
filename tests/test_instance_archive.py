import pathlib
import tempfile
import unittest
import zipfile

from scripts.prepare import discover_minecraft_root, validate_zip
from scripts.extract_instance import extract_safe


class InstanceArchiveTests(unittest.TestCase):
    def test_discovers_nested_minecraft_game_root(self):
        names = [
            "export/.minecraft/versions/26.3/26.3.json",
            "export/.minecraft/assets/indexes/26.json",
        ]
        self.assertEqual(discover_minecraft_root(names), "export/.minecraft")

    def test_rejects_manifest_only_modpack_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "pack.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("manifest.json", "{}")
                zf.writestr("overrides/options.txt", "")
            _, names = validate_zip(archive)
            with self.assertRaisesRegex(ValueError, "versions"):
                discover_minecraft_root(names)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../outside.txt", "no")
            with self.assertRaisesRegex(ValueError, "Unsafe ZIP path"):
                validate_zip(archive)

    def test_rejects_symlink_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "link.zip"
            info = zipfile.ZipInfo("game/link")
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(info, "target")
            with self.assertRaisesRegex(ValueError, "Symlink"):
                validate_zip(archive)

    def test_extracts_game_folder_without_changing_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "instance.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/versions/26.3/26.3.json", "{}")
                zf.writestr("game/assets/indexes/26.json", "{}")
            before = archive.read_bytes()
            game = extract_safe(archive, root / "unpacked")
            self.assertEqual(game, root / "unpacked/game")
            self.assertEqual((game / "versions/26.3/26.3.json").read_text(), "{}")
            self.assertEqual(archive.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
