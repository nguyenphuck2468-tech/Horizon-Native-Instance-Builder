# Outputs

The instance ZIP and compiled runtime are deliberately separate.

- `horizon-instance-zip`: original instance ZIP, byte-for-byte.
- `native-build-linux-x86_64` and `native-build-windows-x86_64`: build logs and discovered candidate outputs.
- `build-report`: input SHA-256 manifest and per-target logs.

Once the runtime archive layout is verified against the selected Horizon revision, the workflow should package it in the exact format accepted by `horizon-launcher import-build <PATH> --trust-unsigned`.
