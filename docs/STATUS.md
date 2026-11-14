# Status and verification boundary

Implemented in the workflow:

- The Horizon instance/data backup ZIP and Minecraft game ZIP are separate inputs.
- The Horizon backup is preserved byte-for-byte; it is not treated as a Minecraft installation.
- ZIP path traversal, duplicate normalized paths and symlink entries are rejected.
- The Minecraft ZIP must contain valid version metadata that references an included asset index; every referenced asset object must exist, be non-empty and match its indexed SHA-1 (verified in bounded-memory streaming), and at least one non-empty library JAR must be present. Metadata-only, directory-only, corrupt and partial asset exports are rejected before extraction.
- The Minecraft archive is extracted safely and its game directory is passed to Horizon's prepare --minecraft.
- Supplied .hnmod files are validated for horizon-native.json and horizon-mixin.toml; an empty mod folder is valid for a core-only build.
- Each .hnmod archive is safely extracted into the directory layout expected by Horizon's native-mod scanner, retaining archive traversal and unsafe-path checks.
- SHA-256 input manifest is generated.
- The workflow resolves the selected Horizon ref once before parallel jobs and checks out that same immutable commit on Linux and Windows.
- A final verification job validates the Linux ELF x86_64 and Windows PE AMD64 executable headers, hashes both stable binaries, and rejects mismatched Horizon commit reports.
- The workflow installs and prepares a published Horizon base, compiles the upstream horizon-client core directly, and invokes native-build only when optional mod bundles are present.
- The Linux runner installs Fontconfig development headers required by the Rust fontconfig-sys dependency.
- The actual platform-specific horizon-client binary is required and uploaded; a launcher-only compile is not counted as success.
- Manual GitHub Actions workflow, read-only token, no secrets, Linux x86_64 and Windows x86_64 jobs.
- A local-only guided build wizard checks the Horizon instance ZIP signature and generates the matching GitHub CLI dispatch command; it does not upload files or replace server-side validation.

Still requires a real Actions run to certify:

- Whether the supplied Minecraft files contain every additional game file pinned by the selected Horizon release.
- Whether the cross-platform verification job completes successfully against actual native binaries.
- Whether the selected native-mod bundles build successfully on both hosted platforms; the core-only path is independent of native mods.
- Whether the resulting binaries import and launch correctly on a user's machine with a compatible prepared base release.

The workflow intentionally does not sign in to a Minecraft account. If the Minecraft ZIP lacks matching game files, Horizon's prepare step must fail with its missing-file/ownership explanation; it must not silently substitute server-engine mode or report a launcher CLI compile as a successful native build.
