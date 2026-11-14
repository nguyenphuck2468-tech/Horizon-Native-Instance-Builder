# Horizon Native Instance Builder

Build a Windows or Linux Horizon client with the newest registry-reviewed native mods that pass the official compatibility check for the exact Horizon Nightly. The output contains a **real `instances/<id>/` game-home directory**, not an archive that must be restored through the launcher.

**Vietnamese guide:** [docs/HUONG-DAN.md](docs/HUONG-DAN.md)

## What this builder does

1. Validates `input/instance/instance.zip` as Horizon instance data (worlds, settings and player data), not as a Java launcher installation.
2. Resolves the immutable commit behind the current official Horizon Nightly.
3. Reads the official Horizon mod registry and its native-health report for that exact Nightly.
4. Downloads the newest compatible registry mods and verifies their SHA-256 and archive manifests.
5. Downloads the Mojang runtime resources Horizon needs, installs the Nightly base, and builds the selected `.hnmod` bundles with Horizon's own native-build command.
6. Refuses mixed-revision builds and refuses to publish a core-only binary as a modded build.
7. Verifies Windows and Linux builds, then unpacks the supplied instance data into a real `instances/<id>/` folder in the output artifact.

## Inputs

    input/
      instance/
        instance.zip       # Horizon instance data
        horizon.zip        # accepted legacy filename
      mods/
        *.hnmod            # original user-supplied bundles; kept for audit/backup

The workflow fetches the current selected registry versions into `input/mods-latest/` on the runner. Original `input/mods/` files are not overwritten.

The current requested mod IDs are:

- appleskin
- hud_plus
- fast_items
- fullbright_horizon
- jade
- jei
- zoom
- enchantmenthints
- inventory_profiles

Freecam and Inventory Profiles are retained as candidates where present in the registry, but are omitted on Nightly `9f42064` because the official compatibility check found unresolved targets. The actual selected set is recorded in `registry-mod-selection` and the build manifest.

## Horizon runtime resources

Horizon is a Rust client. The instance data and the runtime resources it needs are separate. The builder downloads the runtime files from Mojang to prepare the Nightly; it does not interpret the instance backup as a Minecraft Java installation and does not rewrite world files.

By default, the runner downloads version 26.3 from Mojang and validates metadata, client data, libraries and assets. The downloaded runtime archive stays on the ephemeral runner.

## Run

Open **Actions → Build Horizon Native Instance → Run workflow**.

- `instance_release_tag`: optional Release tag containing the instance backup.
- `instance_asset_name`: backup filename, default `instance.zip`.
- `minecraft_version`: runtime version, default `26.3`; it must match the selected Nightly's lock.
- Leave `minecraft_release_tag` blank for the normal Mojang download.

The Horizon source commit and compatible mod set are resolved automatically.

## Output

The workflow uploads:

- `horizon-instance-windows-x86_64`
- `horizon-instance-linux-x86_64`
- `native-build-verification`
- `registry-mod-selection`
- `input-inspection-report`
- `horizon-instance-zip`

Extract the Windows or Linux artifact **once**. Its root contains:

- `instances/horizon-native-<commit7>/...`: the actual instance game-home directory, ready to copy into Horizon's existing `GAME_HOME/instances/` folder.
- `native-build/<target>/horizon-client[.exe]`: the platform-specific native client.
- `build-inputs/mods/*.hnmod`: exact native-mod inputs used for provenance.
- `build-manifest.json`: source commit, instance archive checksum, file counts and SHA-256 hashes.
- `README-INSTALL.txt`: platform-specific installation steps.

### Install on Windows

1. Copy the extracted `instances/horizon-native-<commit7>` folder into Horizon's existing `GAME_HOME/instances/` directory. Do not put it in the launcher's program folder.
2. Open PowerShell in the extracted artifact folder and run:

       $build = horizon-launcher --json import-build "native-build/windows-x86_64/horizon-client.exe" --trust-unsigned | ConvertFrom-Json
       horizon-launcher instance version "horizon-native-<commit7>" $build.imported
       horizon-launcher instance select "horizon-native-<commit7>"

   Replace `<commit7>` with the exact folder name from the artifact. The JSON result supplies the real imported version tag; it is date- and binary-hash-based, not the Horizon source commit.
3. Open Horizon Launcher. The new instance should appear in its instance list and use the imported native client.

The instance directory itself is a direct drop-in. The separate import and pin commands are required because Horizon stores native versions and instance metadata outside `GAME_HOME/instances/`; putting an executable inside the instance folder would not register it.

### Install on Linux

Copy the extracted `instances/horizon-native-<commit7>` folder into `GAME_HOME/instances/`, then run the equivalent commands using `native-build/linux-x86_64/horizon-client`.

## Security and limits

Native mods are Rust code, not sandboxed scripts; they run with the permissions of the user who launches Horizon. Registry review and SHA-256 checks establish provenance and integrity, not harmlessness. Only import builds and mods you trust.

Linux x86_64 and Windows x86_64 are configured. macOS remains unverified. A successful compile is not proof of runtime compatibility; test the imported client before relying on it with important worlds.
