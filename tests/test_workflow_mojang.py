import pathlib
import unittest


class MojangWorkflowTests(unittest.TestCase):
    def test_workflow_downloads_from_mojang_by_default(self):
        workflow = (
            pathlib.Path(__file__).resolve().parents[1]
            / ".github/workflows/build.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('minecraft_version:', workflow)
        self.assertIn('default: "26.3"', workflow)
        self.assertIn('required: false', workflow.split('minecraft_release_tag:', 1)[1].split('minecraft_source_repository:', 1)[0])
        self.assertIn('python scripts/download_minecraft.py --version "$VERSION" --expected-version "$EXPECTED_VERSION" --output input/minecraft/minecraft.zip', workflow)
        self.assertIn("Read Minecraft version pinned by Horizon", workflow)
        self.assertIn("if: ${{ inputs.minecraft_release_tag == '' }}", workflow)
        self.assertIn("if: ${{ inputs.minecraft_release_tag != '' }}", workflow)

    def test_public_validation_artifact_never_contains_minecraft_game_zip(self):
        workflow = (
            pathlib.Path(__file__).resolve().parents[1]
            / ".github/workflows/build.yml"
        ).read_text(encoding="utf-8")
        artifact = workflow.split("name: validated-inputs", 1)[1].split("native-build:", 1)[0]
        self.assertIn("input/instance/instance.zip", artifact)
        self.assertIn("input/mods/", artifact)
        self.assertNotIn("input/minecraft/minecraft.zip", artifact)


if __name__ == "__main__":
    unittest.main()
