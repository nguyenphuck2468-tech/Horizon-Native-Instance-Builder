# Outputs

The instance ZIP and compiled native client are separate deliverables.

- horizon-instance-zip: original instance ZIP, byte-for-byte.
- native-build-linux-x86_64: the Linux horizon-client binary plus build logs and reports.
- native-build-windows-x86_64: the Windows horizon-client.exe binary plus build logs and reports.
- build-report: input SHA-256 manifest and per-target build facts/logs.

The native client binary is imported on a player's machine with horizon-launcher import-build <PATH> --trust-unsigned. That command copies the player's installed base release's game files and installs the binary as its own version. The original instance ZIP is imported separately when its worlds/settings are needed.
