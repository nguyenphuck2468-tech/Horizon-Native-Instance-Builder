# Outputs

The Horizon instance ZIP and compiled native client are separate deliverables. The Minecraft game ZIP is used only as preparation input.

- horizon-instance-zip: original Horizon instance/data backup ZIP, byte-for-byte.
- native-build-linux-x86_64: the Linux horizon-client binary plus build logs and reports.
- native-build-windows-x86_64: the Windows horizon-client.exe binary plus build logs and reports.
- build-report: SHA-256 manifest for both ZIP inputs and the native-mod bundles, plus per-target build facts/logs.

The native client binary is imported on a player's machine with horizon-launcher import-build <PATH> --trust-unsigned. That command copies the player's installed base release's game files and installs the binary as its own version. The original Horizon instance ZIP is imported separately when its worlds/settings are needed.
