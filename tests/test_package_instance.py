import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.package_instance import package


class PackageInstanceTests(unittest.TestCase):
    def test_package_keeps_original_instance_and_includes_client_and_mods(self):
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
            self.assertEqual(len(result["mods"]), 1)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read("instance/instance.zip"), instance.read_bytes())
                self.assertEqual(archive.read("native/windows-x86_64/horizon-client.exe"),
                                 binary.read_bytes())
                self.assertEqual(archive.read("mods/example.hnmod"), b"native mod bundle")
                self.assertIsNone(archive.testzip())


if __name__ == "__main__":
    unittest.main()
