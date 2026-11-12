import tempfile
import struct
import unittest
from pathlib import Path

from scripts.verify_native_artifacts import verify_artifacts

class NativeArtifactVerificationTests(unittest.TestCase):
    def _fixture(self, root: Path, commit: str = "a" * 40):
        inputs = root / "inputs"
        inputs.joinpath("build-report").mkdir(parents=True)
        inputs.joinpath("build-report", "horizon-commit.txt").write_text(
            commit + "\n", encoding="ascii"
        )
        linux = root / "linux"
        windows = root / "windows"
        for base, target, client in (
            (linux, "linux-x86_64", "horizon-client"),
            (windows, "windows-x86_64", "horizon-client.exe"),
        ):
            report = base / "build-report" / target
            report.mkdir(parents=True)
            report.joinpath("build.txt").write_text(
                f"Horizon commit: {commit}\nTarget: {target}\nRunner: test\n",
                encoding="utf-8",
            )
            runtime = base / "native-runtime"
            runtime.mkdir()
            if target == "linux-x86_64":
                binary = bytearray(64)
                binary[:4] = b"\\x7fELF"
                binary[4:7] = bytes((2, 1, 1))
                struct.pack_into("<H", binary, 18, 62)
            else:
                binary = bytearray(0x86)
                binary[:2] = b"MZ"
                struct.pack_into("<I", binary, 0x3C, 0x80)
                binary[0x80:0x84] = b"PE\\x00\\x00"
                struct.pack_into("<H", binary, 0x84, 0x8664)
            runtime.joinpath(client).write_bytes(binary)
        return inputs, linux, windows

    def test_verifies_both_platforms_and_emits_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            inputs, linux, windows = self._fixture(Path(temp))
            result = verify_artifacts(inputs, linux, windows)
            self.assertEqual(result["status"], "VERIFIED")
            self.assertEqual(result["horizon_commit"], "a" * 40)
            self.assertEqual(set(result["targets"]), {"linux-x86_64", "windows-x86_64"})
            for target in result["targets"].values():
                self.assertGreater(target["bytes"], 0)
                self.assertEqual(len(target["sha256"]), 64)

    def test_rejects_wrong_native_machine_architecture(self):
        with tempfile.TemporaryDirectory() as temp:
            inputs, linux, windows = self._fixture(Path(temp))
            binary = windows / "native-runtime" / "horizon-client.exe"
            data = bytearray(binary.read_bytes())
            struct.pack_into("<H", data, 0x84, 0x014C)  # 32-bit x86
            binary.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "expected PE AMD64"):
                verify_artifacts(inputs, linux, windows)

    def test_rejects_non_executable_payload_with_valid_size(self):
        with tempfile.TemporaryDirectory() as temp:
            inputs, linux, windows = self._fixture(Path(temp))
            binary = linux / "native-runtime" / "horizon-client"
            binary.write_bytes(b"not-an-ELF-binary".ljust(64, b"\\x00"))
            with self.assertRaisesRegex(ValueError, "not an ELF executable"):
                verify_artifacts(inputs, linux, windows)

    def test_rejects_platform_built_from_different_horizon_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            inputs, linux, windows = self._fixture(Path(temp))
            report = windows / "build-report" / "windows-x86_64" / "build.txt"
            report.write_text(
                f"Horizon commit: {'b' * 40}\nTarget: windows-x86_64\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Horizon commit mismatch"):
                verify_artifacts(inputs, linux, windows)

    def test_rejects_missing_native_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            inputs, linux, windows = self._fixture(Path(temp))
            (windows / "native-runtime" / "horizon-client.exe").unlink()
            with self.assertRaisesRegex(ValueError, "missing native client binary"):
                verify_artifacts(inputs, linux, windows)

    def test_rejects_non_immutable_commit_identifier(self):
        with tempfile.TemporaryDirectory() as temp:
            inputs, linux, windows = self._fixture(Path(temp), "main")
            with self.assertRaisesRegex(ValueError, "full 40-character SHA-1"):
                verify_artifacts(inputs, linux, windows)

if __name__ == "__main__":
    unittest.main()
