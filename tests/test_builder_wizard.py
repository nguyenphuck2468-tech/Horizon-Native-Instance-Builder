import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "tools" / "builder-wizard.html"

class WizardParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.inputs = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "input":
            self.inputs.append(attrs)

class BuilderWizardTests(unittest.TestCase):
    def test_wizard_contains_instance_minecraft_and_dispatch_controls(self):
        source = PAGE.read_text(encoding="utf-8")
        parser = WizardParser()
        parser.feed(source)
        self.assertTrue({
            "instance", "mods", "revision", "tag", "minecraftVersion",
            "command", "copy", "ready",
        }.issubset(parser.ids))
    def test_wizard_is_local_only_and_does_not_upload_or_execute_native_code(self):
        source = PAGE.read_text(encoding="utf-8").lower()
        self.assertNotIn("<script src=", source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("xmlhttprequest", source)
        self.assertNotIn("formaction=", source)
        self.assertIn("does not upload files", source)
        self.assertIn("not sandboxed", source)
    def test_wizard_uses_mojang_download_and_not_a_required_minecraft_zip(self):
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("downloaded directly from Mojang", source)
        self.assertIn("minecraft_version", source)
        self.assertNotIn('id="minecraft" type="file"', source)
        self.assertIn("instance_release_tag", source)
    def test_wizard_explains_instance_zip_upload(self):
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("Upload the selected backup as instance.zip", source)
        self.assertIn("The workflow downloads Minecraft", source)

if __name__ == "__main__":
    unittest.main()
