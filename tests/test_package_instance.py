import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.package_instance import package


class PackageInstanceTests(unittest.TestCase):
    def test_package_contains_a_real_drop_in_instance_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instance = root / "instance.zip"
            with zipfile.ZipFile(instance, "w") as archive:
                archive.writestr("saves/world/level.dat", b"world")
                archive.writestr("options.txt", "renderDistance:8")
            binary = root / "horizon-client.exe"
            binary.write_bytes(b"test executable")
            mods = root / "mods"
            mods.mkdir()
            (mods / "example.hnmod").write_bytes(b"native mod bundle")
            output = root / "bundle.zip"

            result = package(instance, binary, mods, "windows-x86_64",
                             "a" * 40, output)
            instance_id = "horizon-native-aaaaaaa"
            self.assertEqual(result["instance"]["id"], instance_id)
            self.assertEqual(result["instance"]["files"], 2)
            self.assertEqual(len(result["mods"]), 1)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    archive.read(f"instances/{instance_id}/saves/world/level.dat"),
                    b"world",
                )
                self.assertEqual(
                    archive.read(f"instances/{instance_id}/options.txt"),
                    b"renderDistance:8",
                )
                self.assertEqual(
                    archive.read("native-build/windows-x86_64/horizon-client.exe"),
                    binary.read_bytes(),
                )
                self.assertEqual(
                    archive.read("build-inputs/mods/example.hnmod"),
                    b"native mod bundle",
                )
                self.assertNotIn("instance/instance.zip", archive.namelist())
                self.assertIsNone(archive.testzip())

    def test_rejects_zip_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instance = root / "instance.zip"
            with zipfile.ZipFile(instance, "w") as archive:
                archive.writestr("../escape.txt", "bad")
            binary = root / "horizon-client.exe"
            binary.write_bytes(b"test executable")
            mods = root / "mods"
            mods.mkdir()
            with self.assertRaisesRegex(ValueError, "Unsafe instance ZIP entry"):
                package(instance, binary, mods, "windows-x86_64",
                        "b" * 40, root / "bundle.zip")


if __name__ == "__main__":
    unittest.main()
