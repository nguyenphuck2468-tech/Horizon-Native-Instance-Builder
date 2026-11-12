import hashlib
import json
import pathlib
import tempfile
import unittest
import zipfile

from scripts.prepare import discover_minecraft_root, validate_minecraft_archive, validate_minecraft_layout, validate_zip
from scripts.extract_instance import extract_safe


class InstanceArchiveTests(unittest.TestCase):
    def test_discovers_nested_minecraft_game_root(self):
        names = [
            "export/.minecraft/versions/26.3/26.3.json",
            "export/.minecraft/assets/indexes/26.json",
            "export/.minecraft/assets/objects/ab/cdef",
            "export/.minecraft/libraries/org/example/library/1.0/library-1.0.jar",
        ]
        self.assertEqual(discover_minecraft_root(names), "export/.minecraft")
        self.assertEqual(validate_minecraft_layout(names), "export/.minecraft")

    def test_rejects_incomplete_minecraft_game_directory(self):
        names = [
            "game/versions/26.3/26.3.json",
            "game/assets/indexes/26.json",
        ]
        with self.assertRaisesRegex(ValueError, "assets/objects"):
            validate_minecraft_layout(names)

    def _write_complete_minecraft_zip(
        self, archive, include_asset=True, corrupt_asset=False,
        include_client=True, corrupt_client=False,
    ):
        asset_bytes = b"asset"
        asset_hash = hashlib.sha1(asset_bytes).hexdigest()
        client_bytes = b"client-jar"
        client_hash = hashlib.sha1(client_bytes).hexdigest()
        metadata = {
            "assetIndex": {"id": "26.3"},
            "downloads": {
                "client": {"sha1": client_hash, "size": len(client_bytes)}
            },
        }
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("game/versions/26.3/26.3.json", json.dumps(metadata))
            if include_client:
                payload = b"bad-client" if corrupt_client else client_bytes
                zf.writestr("game/versions/26.3/26.3.jar", payload)
            zf.writestr(
                "game/assets/indexes/26.3.json",
                '{"objects":{"icons/icon.png":{"hash":"' + asset_hash + '"}}}',
            )
            if include_asset:
                payload = b"corrupt" if corrupt_asset else asset_bytes
                zf.writestr("game/assets/objects/" + asset_hash[:2] + "/" + asset_hash, payload)
            zf.writestr("game/libraries/org/example/library/1.0/library-1.0.jar", b"jar")

    def test_validates_asset_index_references_and_real_library_files(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "minecraft.zip"
            self._write_complete_minecraft_zip(archive)
            _, names = validate_zip(archive)
            self.assertEqual(validate_minecraft_archive(archive, names), "game")

    def test_rejects_missing_pinned_client_jar(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "minecraft.zip"
            self._write_complete_minecraft_zip(archive, include_client=False)
            _, names = validate_zip(archive)
            with self.assertRaisesRegex(ValueError, "missing the correctly sized client JAR"):
                validate_minecraft_archive(archive, names)

    def test_rejects_client_jar_with_wrong_sha1(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "minecraft.zip"
            self._write_complete_minecraft_zip(archive, corrupt_client=True)
            _, names = validate_zip(archive)
            with self.assertRaisesRegex(ValueError, "client JAR has a SHA-1 mismatch"):
                validate_minecraft_archive(archive, names)

    def test_rejects_missing_asset_referenced_by_index(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "minecraft.zip"
            self._write_complete_minecraft_zip(archive, include_asset=False)
            _, names = validate_zip(archive)
            with self.assertRaisesRegex(ValueError, "missing asset objects"):
                validate_minecraft_archive(archive, names)

    def test_rejects_asset_object_with_wrong_sha1(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "minecraft.zip"
            self._write_complete_minecraft_zip(archive, corrupt_asset=True)
            _, names = validate_zip(archive)
            with self.assertRaisesRegex(ValueError, "SHA-1 mismatch"):
                validate_minecraft_archive(archive, names)

    def test_validates_asset_objects_for_every_included_version(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "minecraft.zip"
            first_bytes = b"first"
            first_hash = hashlib.sha1(first_bytes).hexdigest()
            second_hash = hashlib.sha1(b"second").hexdigest()
            with zipfile.ZipFile(archive, "w") as zf:
                first_client = b"first-client"
                second_client = b"second-client"
                zf.writestr(
                    "game/versions/26.3/26.3.json",
                    json.dumps({
                        "assetIndex": {"id": "26.3"},
                        "downloads": {"client": {
                            "sha1": hashlib.sha1(first_client).hexdigest(),
                            "size": len(first_client),
                        }},
                    }),
                )
                zf.writestr(
                    "game/versions/26.2/26.2.json",
                    json.dumps({
                        "assetIndex": {"id": "26.2"},
                        "downloads": {"client": {
                            "sha1": hashlib.sha1(second_client).hexdigest(),
                            "size": len(second_client),
                        }},
                    }),
                )
                zf.writestr("game/versions/26.3/26.3.jar", first_client)
                zf.writestr("game/versions/26.2/26.2.jar", second_client)
                zf.writestr(
                    "game/assets/indexes/26.3.json",
                    '{"objects":{"first":{"hash":"' + first_hash + '"}}}',
                )
                zf.writestr(
                    "game/assets/indexes/26.2.json",
                    '{"objects":{"second":{"hash":"' + second_hash + '"}}}',
                )
                zf.writestr("game/assets/objects/" + first_hash[:2] + "/" + first_hash, first_bytes)
                zf.writestr(
                    "game/libraries/org/example/library/1.0/library-1.0.jar",
                    b"jar",
                )
            _, names = validate_zip(archive)
            with self.assertRaisesRegex(ValueError, "assets/indexes/26.2.json"):
                validate_minecraft_archive(archive, names)

    def test_rejects_directory_only_assets_and_libraries(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "minecraft.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                client_bytes = b"client-jar"
                zf.writestr(
                    "game/versions/26.3/26.3.json",
                    json.dumps({
                        "assetIndex": {"id": "26.3"},
                        "downloads": {"client": {
                            "sha1": hashlib.sha1(client_bytes).hexdigest(),
                            "size": len(client_bytes),
                        }},
                    }),
                )
                zf.writestr("game/versions/26.3/26.3.jar", client_bytes)
                zf.writestr("game/assets/indexes/26.3.json", '{"objects":{"x":{"hash":"' + "a" * 40 + '"}}}')
                zf.writestr("game/assets/objects/", "")
                zf.writestr("game/libraries/", "")
            _, names = validate_zip(archive)
            with self.assertRaisesRegex(ValueError, "missing asset objects"):
                validate_minecraft_archive(archive, names)

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
