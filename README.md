# Horizon Native Instance Builder

Build a Windows or Linux Horizon client with the newest registry-reviewed native mods that pass the official compatibility check for Horizon's current Nightly. The user's Horizon instance backup is preserved byte-for-byte and packaged with the platform-specific native client.

**Vietnamese guide:** [docs/HUONG-DAN.md](docs/HUONG-DAN.md)

## What this builder does

1. Validates input/instance/instance.zip as a Horizon instance backup. It does not treat this archive as a Java launcher installation or extract it as game runtime files.
2. Resolves the immutable commit behind the current official Horizon Nightly.
3. Reads the official Horizon mod registry and its native-health report for that exact Nightly.
4. Downloads the newest versions of the selected native mods, verifies each registry SHA-256 and archive manifest, and leaves out versions the official health report marks broken.
5. Downloads the Mojang runtime resources Horizon needs, installs the Nightly base, and builds the selected .hnmod bundles with Horizon's own native-build command.
6. Refuses mixed-revision builds. It does not use --allow-version-mismatch and does not publish a core-only binary under a modded-build label.
7. Verifies that Windows and Linux binaries were built from the same Nightly commit, then packages each with the original instance backup and the exact .hnmod files used.

## Inputs

    input/
      instance/
        instance.zip       # Horizon worlds, settings and instance data
        horizon.zip        # accepted legacy filename
      mods/
        *.hnmod            # original user-supplied bundles; kept for audit/backup

The workflow fetches the current selected registry versions into input/mods-latest/ on the runner. The original input/mods/ files are not overwritten and are not used as the latest build set.

The selected mod IDs are:

- appleskin
- basic_hud
- fast_items
- freecam_plus
- freelook
- fullbright_horizon
- jade
- jei
- mod_menu
- zoom

A mod is omitted only when the official health report for the exact Nightly marks its newest registry version broken, or when its registry metadata does not target the configured game version. If the health report is stale or for another Horizon commit, the workflow fails closed rather than guessing.

## Horizon runtime resources

Horizon is a Rust client and uses the same game rules and data format. The instance backup is separate from the runtime resources. The builder downloads the runtime files Horizon needs from Mojang to prepare the Nightly; it does not interpret the instance backup as a Minecraft Java installation, and it does not replace or rewrite the user's worlds.

By default, the runner downloads version 26.3 from Mojang and validates the metadata, client data, libraries and assets. The downloaded runtime archive stays on the ephemeral runner and is not uploaded as an artifact. An optional legacy ZIP input remains available for an already prepared runtime directory.

## Run

Open **Actions → Build Horizon Native Instance → Run workflow**.

- instance_release_tag: optional Release tag containing the instance backup.
- instance_asset_name: backup filename, default instance.zip.
- minecraft_version: runtime version, default 26.3; it must match the selected Horizon Nightly's lock.
- minecraft_release_tag: leave blank for the normal Mojang download. Use only for the legacy prebuilt runtime ZIP path.
- minecraft_source_repository: optional source repository for that legacy ZIP.
- minecraft_asset_name: legacy runtime ZIP filename, default minecraft.zip.

The Horizon source commit and compatible mod set are resolved automatically at the start of the run.

## Output

The workflow uploads:

- horizon-instance-windows-x86_64
- horizon-instance-linux-x86_64
- native-build-verification
- registry-mod-selection
- input-inspection-report
- horizon-instance-zip

Each platform ZIP contains:

- instance/instance.zip: the original Horizon instance backup, byte-for-byte.
- native/<target>/horizon-client[.exe]: the native client built with the selected mods.
- mods/*.hnmod: the exact registry packages included in that build.
- build-manifest.json: source commit, file sizes and SHA-256 hashes.
- README-INSTALL.txt: restore/import instructions.

The bundle keeps the instance and native client together. It is not a replacement instance format that Horizon Launcher opens by double-clicking: restore/import the backup through Horizon's instance flow, then import the native client with:

    horizon-launcher import-build <PATH-TO-horizon-client> --trust-unsigned

## Security and limits

Native mods are Rust code, not sandboxed scripts; they run with the permissions of the user who launches Horizon. The registry review and SHA-256 checks help establish provenance, but do not make native code harmless. Only use mods whose source you trust.

Linux x86_64 and Windows x86_64 are configured. macOS remains unverified. A successful compile is not proof of runtime compatibility; test the imported client before relying on it with important worlds.
