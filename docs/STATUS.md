# Status and known verification gap

Implemented:
- Instance input is a ZIP file, not a directory.
- One or more `.hnmod` files are accepted.
- ZIP path traversal and symlink entries are rejected.
- SHA-256 manifest is generated.
- Instance ZIP is retained as a separate, unchanged artifact.
- Manual GitHub Actions workflow, read-only token, no secrets.
- Linux x86_64 and Windows x86_64 jobs.

Not yet certified on a clean hosted runner:
- Whether `horizon-launcher native-build` can resolve a base game/version without a preinstalled Horizon instance.
- Exact runtime output path and archive layout on both operating systems.
- Whether importing the instance ZIP automatically selects the separately imported native runtime.

The build job therefore retains logs and candidate output paths. It must not be considered a release-ready runtime builder until those three points pass an actual Actions run. A successful compilation of the launcher CLI itself is not proof that a native runtime was built.
