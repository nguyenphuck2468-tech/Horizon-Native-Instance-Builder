import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
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

    def test_rejects_file_used_as_parent_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "file-parent.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/mods", b"not a directory")
                zf.writestr("game/mods/example.jar", b"child")
            with self.assertRaisesRegex(ValueError, "file/directory path collision"):
                validate_zip(archive)

    def test_rejects_directory_replaced_by_file(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "directory-file.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/mods/example.jar", b"child")
                zf.writestr("game/mods", b"not a directory")
            with self.assertRaisesRegex(ValueError, "file/directory path collision"):
                validate_zip(archive)

    def test_extractor_rejects_file_used_as_parent_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "file-parent.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/mods", b"not a directory")
                zf.writestr("game/mods/example.jar", b"child")
            with self.assertRaisesRegex(SystemExit, "file/directory path collision"):
                extract_safe(archive, root / "out")

    def test_rejects_case_insensitive_file_parent_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "casefold-parent.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("Game/Mods", b"file")
                zf.writestr("game/mods/example.jar", b"child")
            with self.assertRaisesRegex(ValueError, "file/directory path collision"):
                validate_zip(archive)

    def test_extractor_rejects_case_insensitive_file_parent_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "casefold-parent.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("Game/Mods", b"file")
                zf.writestr("game/mods/example.jar", b"child")
            with self.assertRaisesRegex(SystemExit, "file/directory path collision"):
                extract_safe(archive, root / "out")

    def test_rejects_case_insensitive_path_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "case-collision.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/Mods/example.jar", b"first")
                zf.writestr("game/mods/EXAMPLE.jar", b"second")
            with self.assertRaisesRegex(ValueError, "Case-insensitive ZIP path collision"):
                validate_zip(archive)

    def test_extractor_rejects_case_insensitive_path_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "case-collision.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/versions/26.3/26.3.json", "{}")
                zf.writestr("game/Versions/26.3/26.3.json", "{}")
            with self.assertRaisesRegex(SystemExit, "Case-insensitive ZIP path collision"):
                extract_safe(archive, root / "out")

    def test_rejects_windows_alternate_stream_device_and_alias_paths(self):
        for unsafe_name in (
            "game/mods/payload:stream",
            "game/CON.txt",
            "game/CON .txt",
            "game/mods/trailing.",
            "game/mods/trailing ",
        ):
            with self.subTest(path=unsafe_name), tempfile.TemporaryDirectory() as temp:
                root = pathlib.Path(temp)
                archive = root / "windows-path.zip"
                with zipfile.ZipFile(archive, "w") as zf:
                    zf.writestr(unsafe_name, b"unsafe")
                with self.assertRaisesRegex(ValueError, "Unsafe ZIP path"):
                    validate_zip(archive)
                with self.assertRaisesRegex(SystemExit, "Unsafe ZIP path"):
                    extract_safe(archive, root / "out")

    def test_preflight_and_extractor_reject_encrypted_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "encrypted.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/payload.bin", b"payload")

            original_infolist = zipfile.ZipFile.infolist

            def encrypted_infolist(instance):
                entries = original_infolist(instance)
                entries[0].flag_bits |= 0x1
                return entries

            with patch.object(zipfile.ZipFile, "infolist", encrypted_infolist):
                with self.assertRaisesRegex(ValueError, "Encrypted ZIP entry refused"):
                    validate_zip(archive)
                with self.assertRaisesRegex(SystemExit, "Encrypted ZIP entry refused"):
                    extract_safe(archive, root / "out")
            self.assertFalse((root / "out").exists())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../outside.txt", "no")
            with self.assertRaisesRegex(ValueError, "Unsafe ZIP path"):
                validate_zip(archive)

    def test_extractor_rejects_path_traversal_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "unsafe.zip"
            destination = root / "out"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../outside.txt", "no")
            with self.assertRaisesRegex(SystemExit, "Unsafe ZIP path"):
                extract_safe(archive, destination)
            self.assertFalse(destination.exists())
            self.assertFalse((root / "outside.txt").exists())

    def test_extractor_rejects_symlink_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "link.zip"
            destination = root / "out"
            info = zipfile.ZipInfo("game/link")
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(info, "target")
            with self.assertRaisesRegex(SystemExit, "Symlink entry refused"):
                extract_safe(archive, destination)
            self.assertFalse(destination.exists())

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

    def test_preflight_and_extractor_reject_special_and_mismatched_entry_types(self):
        cases = (
            ("game/fifo", 0o010644, b"special", "Unsupported special ZIP entry"),
            ("game/directory-mode", 0o040755, b"", "directory mode/name mismatch"),
            ("game/file-mode/", 0o100644, b"", "file mode/name mismatch"),
        )
        for name, unix_mode, payload, message in cases:
            with self.subTest(path=name), tempfile.TemporaryDirectory() as temp:
                root = pathlib.Path(temp)
                archive = root / "entry-type.zip"
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = unix_mode << 16
                with zipfile.ZipFile(archive, "w") as zf:
                    zf.writestr(info, payload)
                with self.assertRaisesRegex(ValueError, message):
                    validate_zip(archive)
                with self.assertRaisesRegex(SystemExit, message):
                    extract_safe(archive, root / "out")

    def test_preflight_rejects_too_many_zip_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "many.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("one.txt", b"1")
                zf.writestr("two.txt", b"2")
            with patch("scripts.prepare.MAX_ARCHIVE_ENTRIES", 1):
                with self.assertRaisesRegex(ValueError, "too many entries"):
                    validate_zip(archive)

    def test_preflight_rejects_excessive_uncompressed_size(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "large.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("payload.bin", b"12345")
            with patch("scripts.prepare.MAX_TOTAL_UNCOMPRESSED_BYTES", 4):
                with self.assertRaisesRegex(ValueError, "total uncompressed size limit"):
                    validate_zip(archive)

    def test_preflight_rejects_oversized_single_member(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "member.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("payload.bin", b"12345")
            with patch("scripts.prepare.MAX_MEMBER_UNCOMPRESSED_BYTES", 4):
                with self.assertRaisesRegex(ValueError, "member exceeds"):
                    validate_zip(archive)

    def test_extractor_rejects_excessive_uncompressed_size(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "large.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/versions/26.3/26.3.json", b"12345")
            with patch("scripts.extract_instance.MAX_TOTAL_UNCOMPRESSED_BYTES", 4):
                with self.assertRaisesRegex(SystemExit, "total uncompressed size limit"):
                    extract_safe(archive, root / "out")

    def test_extractor_rejects_too_many_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "many.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("one.txt", b"1")
                zf.writestr("two.txt", b"2")
            with patch("scripts.extract_instance.MAX_ARCHIVE_ENTRIES", 1):
                with self.assertRaisesRegex(SystemExit, "too many entries"):
                    extract_safe(archive, root / "out")

    def test_extractor_preflights_all_entries_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "late-unsafe.zip"
            destination = root / "out"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/safe.txt", b"safe")
                zf.writestr("../outside.txt", b"unsafe")
            with self.assertRaisesRegex(SystemExit, "Unsafe ZIP path"):
                extract_safe(archive, destination)
            self.assertFalse(destination.exists())
            self.assertFalse((destination / "game" / "safe.txt").exists())

    def test_extractor_rolls_back_files_after_midstream_read_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "partial.zip"
            destination = root / "out"
            destination.mkdir()
            sentinel = destination / "keep.txt"
            sentinel.write_text("pre-existing", encoding="utf-8")
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/versions/26.3/26.3.json", "{}")
                zf.writestr("game/a.bin", b"first payload")
                zf.writestr("game/b.bin", b"second payload")

            original_read = zipfile.ZipExtFile.read

            def fail_second_member(member, size=-1):
                if member.name == "game/b.bin":
                    raise zipfile.BadZipFile("simulated CRC/read failure")
                return original_read(member, size)

            with patch.object(zipfile.ZipExtFile, "read", fail_second_member):
                with self.assertRaisesRegex(zipfile.BadZipFile, "simulated CRC"):
                    extract_safe(archive, destination)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "pre-existing")
            self.assertFalse((destination / "game").exists())
            self.assertEqual(list(destination.iterdir()), [sentinel])

    def test_extractor_removes_new_destination_after_midstream_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "partial.zip"
            destination = root / "new" / "out"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/versions/26.3/26.3.json", "{}")
                zf.writestr("game/a.bin", b"first payload")
                zf.writestr("game/b.bin", b"second payload")

            original_read = zipfile.ZipExtFile.read

            def fail_second_member(member, size=-1):
                if member.name == "game/b.bin":
                    raise zipfile.BadZipFile("simulated CRC/read failure")
                return original_read(member, size)

            with patch.object(zipfile.ZipExtFile, "read", fail_second_member):
                with self.assertRaisesRegex(zipfile.BadZipFile, "simulated CRC"):
                    extract_safe(archive, destination)

            self.assertFalse(destination.exists())
            self.assertFalse((root / "new").exists())

    def test_extractor_rejects_symlink_destination_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "instance.zip"
            target = root / "redirected"
            target.mkdir()
            destination = root / "out"
            destination.symlink_to(target, target_is_directory=True)
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/versions/26.3/26.3.json", "{}")
            with self.assertRaisesRegex(SystemExit, "symlink extraction destination"):
                extract_safe(archive, destination)
            self.assertEqual(list(target.iterdir()), [])

    def test_extractor_rejects_existing_symlink_inside_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "symlink-parent.zip"
            destination = root / "out"
            destination.mkdir()
            (destination / "real").mkdir()
            (destination / "game").symlink_to(destination / "real", target_is_directory=True)
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/payload.txt", b"must not follow symlink")
            with self.assertRaisesRegex(SystemExit, "Existing symlink"):
                extract_safe(archive, destination)
            self.assertFalse((destination / "real" / "payload.txt").exists())

    def test_extractor_refuses_encrypted_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "encrypted.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                info = zipfile.ZipInfo("game/payload.txt")
                info.flag_bits |= 0x1
                zf.writestr(info, b"encrypted")
            # ZIP writers may normalize unsupported encryption flags. Exercise the validator
            # through a patched ZipInfo flag to keep this test independent of a crypto backend.
            original = zipfile.ZipFile.infolist

            def encrypted_infolist(zf):
                entries = original(zf)
                entries[0].flag_bits |= 0x1
                return entries

            with patch.object(zipfile.ZipFile, "infolist", encrypted_infolist):
                with self.assertRaisesRegex(SystemExit, "Encrypted ZIP entry"):
                    extract_safe(archive, root / "out")

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


    def test_rejects_unicode_canonical_file_parent_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "unicode-parent.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/caf\u00e9", b"file")
                zf.writestr("game/cafe\u0301/child.txt", b"child")
            with self.assertRaisesRegex(ValueError, "file/directory path collision"):
                validate_zip(archive)
            with self.assertRaisesRegex(SystemExit, "file/directory path collision"):
                extract_safe(archive, root / "out")

    def test_rejects_unicode_canonical_equivalent_path_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = pathlib.Path(temp) / "unicode-collision.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/caf\u00e9.txt", b"composed")
                zf.writestr("game/cafe\u0301.txt", b"decomposed")
            with self.assertRaisesRegex(ValueError, "Case-insensitive ZIP path collision"):
                validate_zip(archive)

    def test_extractor_rejects_unicode_canonical_equivalent_path_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            archive = root / "unicode-collision.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("game/versions/26.3/26.3.json", "{}")
                zf.writestr("game/caf\u00e9.txt", b"composed")
                zf.writestr("game/cafe\u0301.txt", b"decomposed")
            with self.assertRaisesRegex(SystemExit, "Case-insensitive ZIP path collision"):
                extract_safe(archive, root / "out")


if __name__ == "__main__":
    unittest.main()