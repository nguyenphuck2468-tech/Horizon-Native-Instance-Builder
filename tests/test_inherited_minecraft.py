import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from scripts import prepare

class InheritedMinecraftValidationTests(unittest.TestCase):
    def test_child_version_can_inherit_client_and_asset_index(self):
        client = b"parent-client-jar"
        asset = b"asset-bytes"
        asset_hash = hashlib.sha1(asset).hexdigest()
        client_hash = hashlib.sha1(client).hexdigest()
        parent = {"id": "parent", "downloads": {"client": {"sha1": client_hash, "size": len(client)}}, "assetIndex": {"id": "idx"}}
        child = {"id": "child", "inheritsFrom": "parent"}
        index = {"objects": {"icons/icon.png": {"hash": asset_hash, "size": len(asset)}}}
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "minecraft.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("versions/child/child.json", json.dumps(child))
                archive.writestr("versions/parent/parent.json", json.dumps(parent))
                archive.writestr("versions/parent/parent.jar", client)
                archive.writestr("assets/indexes/idx.json", json.dumps(index))
                archive.writestr(f"assets/objects/{asset_hash[:2]}/{asset_hash}", asset)
                archive.writestr("libraries/example/library.jar", b"library")
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
            self.assertEqual(prepare.validate_minecraft_archive(path, names), ".")

if __name__ == "__main__":
    unittest.main()
