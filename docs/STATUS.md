# Status and verification boundary

Implemented in the workflow:

- Instance input is a ZIP file, not a directory; instance.zip and legacy horizon.zip names are accepted.
- ZIP path traversal, duplicate normalized paths and symlink entries are rejected.
- The ZIP must contain a Minecraft versions/<version>/<version>.json layout.
- The archive is extracted safely and its game directory is passed to Horizon's prepare --minecraft.
- One or more .hnmod files are validated for horizon-native.json and horizon-mixin.toml.
- SHA-256 input manifest is generated.
- The original instance ZIP is retained byte-for-byte as a separate artifact.
- The workflow builds the launcher CLI from the selected revision of nguyenphuck2468-tech/horizon.
- The workflow installs and prepares a published Horizon base before invoking the client native-build command.
- The actual platform-specific horizon-client binary is required and uploaded; a launcher-only compile is not counted as success.
- Manual GitHub Actions workflow, read-only token, no secrets, Linux x86_64 and Windows x86_64 jobs.

Still requires a real Actions run to certify:

- Whether the supplied instance archive contains all game files pinned by the selected Horizon release.
- Whether the selected native-mod bundles build successfully on both hosted platforms.
- Whether the resulting binaries import and launch correctly on a user's machine with a compatible prepared base release.

The workflow intentionally does not sign in to a Minecraft account. If the ZIP lacks matching game files, Horizon's prepare step must fail with its missing-file/ownership explanation; it must not silently substitute server-engine mode or report a launcher CLI compile as a successful native build.
