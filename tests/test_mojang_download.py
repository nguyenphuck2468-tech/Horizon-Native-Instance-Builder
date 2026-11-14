import hashlib
import json
import pathlib
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from scripts import download_minecraft


class MojangDownloadTests(unittest.TestCase):
    def test_rejects_non_https_and_path_traversal(self):
        with self.assertRaisesRegex(ValueError, "non-official"):
            download_minecraft._validate_url("http://example.invalid/file")
        with self.assertRaisesRegex(ValueError, "non-official"):
            download_minecraft._validate_url("https://example.invalid/file")
        for path in ("../escape.jar", "/absolute.jar", "a\\..\\b.jar", "CON/file.jar"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                download_minecraft._safe_relative_path(path)

    def test_legacy_maven_coordinate_uses_official_library_repository(self):
        result = list(download_minecraft._library_downloads({"name": "org.example:sample:1.2.3"}))
        self.assertEqual(result[0]["path"], "org/example/sample/1.2.3/sample-1.2.3.jar")
        self.assertEqual(
            result[0]["url"],
            "https://libraries.minecraft.net/org/example/sample/1.2.3/sample-1.2.3.jar",
        )

    def test_download_game_builds_verified_minecraft_directory_zip(self):
        client = b"official-client-jar"
        library = b"official-library-jar"
        asset = b"official-asset"
        client_sha = hashlib.sha1(client).hexdigest()
        library_sha = hashlib.sha1(library).hexdigest()
        asset_sha = hashlib.sha1(asset).hexdigest()
        index = {"objects": {"icons/icon.png": {"hash": asset_sha, "size": len(asset)}}}
        metadata = {
            "id": "1.21.1",
            "downloads": {"client": {"url": "https://launcher.mojang.com/client.jar", "size": len(client), "sha1": client_sha}},
            "assetIndex": {"id": "1.21", "url": "https://piston-meta.mojang.com/index.json", "size": 1, "sha1": "index-sha"},
            "libraries": [{"downloads": {"artifact": {
                "path": "org/example/sample/1.0/sample-1.0.jar",
                "url": "https://libraries.minecraft.net/org/example/sample/1.0/sample-1.0.jar",
                "size": len(library), "sha1": library_sha,
            }}}],
        }
        manifest = {
            "latest": {"release": "1.21.1", "snapshot": "snapshot"},
            "versions": [{"id": "1.21.1", "url": "https://piston-meta.mojang.com/version.json", "size": 2, "sha1": "meta-sha"}],
        }
        payloads = {
            download_minecraft.MANIFEST_URL: json.dumps(manifest).encode(),
            "https://piston-meta.mojang.com/version.json": json.dumps(metadata).encode(),
            "https://piston-meta.mojang.com/index.json": json.dumps(index).encode(),
        }

        def fake_read(url, *args, **kwargs):
            return payloads[url]

        def fake_write(root, relative, url, size=None, sha1=None):
            data = {
                "https://launcher.mojang.com/client.jar": client,
                "https://libraries.minecraft.net/org/example/sample/1.0/sample-1.0.jar": library,
                f"https://resources.download.minecraft.net/{asset_sha[:2]}/{asset_sha}": asset,
            }[url]
            target = pathlib.Path(root) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return target

        with tempfile.TemporaryDirectory() as temp:
            output = pathlib.Path(temp) / "minecraft.zip"
            with patch.object(download_minecraft, "_read_url", side_effect=fake_read), patch.object(
                download_minecraft, "_write_verified", side_effect=fake_write
            ):
                selected = download_minecraft.download_game("latest-release", output)
            self.assertEqual(selected, "1.21.1")
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("versions/1.21.1/1.21.1.json", names)
                self.assertIn("versions/1.21.1/1.21.1.jar", names)
                self.assertIn("libraries/org/example/sample/1.0/sample-1.0.jar", names)
                self.assertIn(f"assets/objects/{asset_sha[:2]}/{asset_sha}", names)

    def test_failed_archive_write_preserves_previous_output(self):
        client = b"official-client-jar"
        client_sha = hashlib.sha1(client).hexdigest()
        metadata = {
            "id": "1.21.1",
            "downloads": {
                "client": {
                    "url": "https://launcher.mojang.com/client.jar",
                    "size": len(client),
                    "sha1": client_sha,
                }
            },
        }
        manifest = {
            "latest": {"release": "1.21.1", "snapshot": "snapshot"},
            "versions": [{
                "id": "1.21.1",
                "url": "https://piston-meta.mojang.com/version.json",
                "size": 1,
                "sha1": "meta-sha",
            }],
        }
        payloads = {
            download_minecraft.MANIFEST_URL: json.dumps(manifest).encode(),
            "https://piston-meta.mojang.com/version.json": json.dumps(metadata).encode(),
        }

        def fake_read(url, *args, **kwargs):
            return payloads[url]

        def fake_write(root, relative, url, size=None, sha1=None):
            target = pathlib.Path(root) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(client)
            return target

        with tempfile.TemporaryDirectory() as temp:
            output = pathlib.Path(temp) / "minecraft.zip"
            output.write_bytes(b"previous archive")
            with patch.object(download_minecraft, "_read_url", side_effect=fake_read), patch.object(
                download_minecraft, "_write_verified", side_effect=fake_write
            ), patch.object(
                download_minecraft.zipfile,
                "ZipFile",
                side_effect=OSError("simulated archive failure"),
            ):
                with self.assertRaisesRegex(OSError, "simulated archive failure"):
                    download_minecraft.download_game("latest-release", output)

            self.assertEqual(output.read_bytes(), b"previous archive")
            self.assertEqual(list(pathlib.Path(temp).glob(".minecraft.zip.*.part")), [])

    def test_rejects_unknown_version_before_creating_archive(self):
        manifest = {"latest": {"release": "1.0", "snapshot": "1.0"}, "versions": []}
        with tempfile.TemporaryDirectory() as temp:
            output = pathlib.Path(temp) / "minecraft.zip"
            with patch.object(download_minecraft, "_read_url", return_value=json.dumps(manifest).encode()):
                with self.assertRaisesRegex(ValueError, "not present"):
                    download_minecraft.download_game("does-not-exist", output)
            self.assertFalse(output.exists())


    def test_write_verified_retries_integrity_mismatch_and_cleans_part_file(self):
        import io
        import time
        class Response:
            def __init__(self, payload):
                self.stream = io.BytesIO(payload)
                self.headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return "https://launcher.mojang.com/client.jar"
            def read(self, size): return self.stream.read(size)
        payload = b"good-client"
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            with patch.object(download_minecraft.urllib.request, "urlopen", side_effect=[Response(b"bad"), Response(payload)]) as opened, patch.object(download_minecraft.time, "sleep"):
                result = download_minecraft._write_verified(root, "versions/test/test.jar", "https://launcher.mojang.com/client.jar", len(payload), hashlib.sha1(payload).hexdigest())
            self.assertEqual(result.read_bytes(), payload)
            self.assertEqual(opened.call_count, 2)
            self.assertFalse(result.with_name(result.name + ".part").exists())

if __name__ == "__main__":
    unittest.main()
