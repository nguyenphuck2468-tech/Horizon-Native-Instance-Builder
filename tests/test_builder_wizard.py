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
    def test_wizard_contains_required_input_and_dispatch_controls(self):
        source = PAGE.read_text(encoding="utf-8")
        parser = WizardParser()
        parser.feed(source)
        self.assertTrue({
            "instance", "minecraft", "mods", "revision", "tag", "asset",
            "command", "copy", "ready",
        }.issubset(parser.ids))

    def test_wizard_is_local_only_and_does_not_execute_or_upload_native_code(self):
        source = PAGE.read_text(encoding="utf-8").lower()
        self.assertNotIn("<script src=", source)
        self.assertNotIn("fetch(", source)
        self.assertNotIn("xmlhttprequest", source)
        self.assertNotIn("formaction=", source)
        self.assertIn("does not upload files", source)
        self.assertIn("not sandboxed", source)

    def test_wizard_explains_the_two_distinct_required_archives(self):
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("Horizon instance backup", source)
        self.assertIn("Full Minecraft game directory", source)
        self.assertIn("instance_release_tag", source)
        self.assertIn("minecraft_release_tag", source)


if __name__ == "__main__":
    unittest.main()
