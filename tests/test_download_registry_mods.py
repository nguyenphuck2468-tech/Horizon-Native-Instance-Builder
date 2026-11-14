import hashlib
import io
import json
import unittest
import zipfile

from scripts.download_registry_mods import choose_versions, validate_bundle


class RegistryModSelectionTests(unittest.TestCase):
    def make_index(self, published="2026-11-08"):
        return {
            "projects": [{
                "id": "sample",
                "kind": "native-mod",
                "versions": [{
                    "version": "1.2.0",
                    "published": published,
                    "game": "26.3",
                    "file": {
                        "name": "sample-1.2.0.hnmod",
                        "url": "https://github.com/example/sample/releases/download/v1.2.0/sample-1.2.0.hnmod",
                        "size": 100,
                        "sha256": "a" * 64,
                    },
                }],
            }],
            "revoked": [],
        }

    def test_selects_latest_version_when_health_report_matches(self):
        selected, skipped = choose_versions(
            self.make_index(),
            {"horizon": "1" * 40, "broken": {}},
            "2026-11-14T00:09:00Z",
            ("sample",),
            "26.3",
            "1" * 40,
        )
        self.assertEqual([item["version"] for item in selected], ["1.2.0"])
        self.assertEqual(skipped, [])

    def test_skips_version_marked_broken_on_latest_nightly(self):
        selected, skipped = choose_versions(
            self.make_index(),
            {"horizon": "1" * 40, "broken": {"sample": {
                "version": "1.2.0", "code": "E_TARGET_NOT_FOUND", "stage": "apply"
            }}},
            "2026-11-14T00:09:00Z",
            ("sample",),
            "26.3",
            "1" * 40,
        )
        self.assertEqual(selected, [])
        self.assertIn("E_TARGET_NOT_FOUND", skipped[0]["reason"])

    def test_refuses_health_report_for_another_horizon_commit(self):
        with self.assertRaisesRegex(ValueError, "not the selected Nightly"):
            choose_versions(
                self.make_index(),
                {"horizon": "2" * 40, "broken": {}},
                "2026-11-14T00:09:00Z",
                ("sample",),
                "26.3",
                "1" * 40,
            )

    def test_refuses_mod_published_after_health_report_date(self):
        with self.assertRaisesRegex(ValueError, "not demonstrably before"):
            choose_versions(
                self.make_index("2026-11-14"),
                {"horizon": "1" * 40, "broken": {}},
                "2026-11-14T00:09:00Z",
                ("sample",),
                "26.3",
                "1" * 40,
            )

    def test_bundle_manifest_must_match_registry(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("horizon-native.json", json.dumps({
                "id": "sample", "version": "1.2.0", "game": "26.3"
            }))
            archive.writestr("mixins/sample/horizon-mixin.toml", "[mod]\nid = \\"sample\\"\\n")
        data = payload.getvalue()
        expected = {
            "id": "sample",
            "version": "1.2.0",
            "game": "26.3",
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        validate_bundle(data, expected)
        expected["version"] = "9.9.9"
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_bundle(data, expected)


if __name__ == "__main__":
    unittest.main()
