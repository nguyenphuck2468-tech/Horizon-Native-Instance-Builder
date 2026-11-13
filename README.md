# Horizon Native Instance Builder

A forkable GitHub Actions project. It consumes two different ZIP files: a Horizon instance/data backup and a full Minecraft game directory. Native mods are one or more .hnmod files.

**Start here:** [Vietnamese usage guide](docs/HUONG-DAN.md).

## Input layout

    input/
      instance/
        instance.zip       # preferred name for the Horizon backup
        horizon.zip        # legacy name, normalized by workflow
      minecraft/
        minecraft.zip      # full Minecraft game directory, required for native build
      mods/
        mod-one.hnmod
        mod-two.hnmod

The existing Horizon instance ZIP is preserved byte-for-byte as a separate artifact. It may contain Horizon settings, worlds, logs or launcher data; it is not assumed to contain the actual Minecraft client files.

The native build also needs a separate Minecraft game ZIP. It must contain the official game-file layout, including versions/<version>/<version>.json and the matching assets/libraries. A complete .minecraft directory is suitable. A Horizon data backup, or a Modrinth/CurseForge export containing only a manifest and overrides, is not a substitute.

Put trusted .hnmod files in input/mods/. Then run Actions → Build Horizon Native Instance → Run workflow. The workflow can download the Horizon backup from this repository's Release assets using instance_release_tag / instance_asset_name. For the Minecraft ZIP, set minecraft_release_tag / minecraft_asset_name and optionally minecraft_source_repository. If the source repository differs from this repository, add the MINECRAFT_INPUTS_TOKEN Actions secret with read-only Contents access to that source repository.

**Important:** this repository is public. Do not upload a copyrighted Minecraft game archive to a public Release asset. Store the game ZIP as an asset in a separate private repository and use minecraft_source_repository plus MINECRAFT_INPUTS_TOKEN.

## What the workflow builds

For Linux x86_64 and Windows x86_64, the workflow:

1. Validates both ZIPs, their paths, and each native-mod bundle.
2. Extracts the Minecraft game ZIP safely and passes its game directory to Horizon's prepare --minecraft command.
3. Checks out the selected revision of nguyenphuck2468-tech/horizon and builds its launcher CLI.
4. Installs the latest published Horizon base, prepares it from the supplied Minecraft files, and invokes horizon-launcher native-build with the trusted .hnmod bundles.
5. Publishes the actual horizon-client / horizon-client.exe binary, build logs and the original Horizon instance ZIP as separate artifacts.

The workflow does not attempt a Minecraft account sign-in. The Minecraft ZIP must include the files pinned by the selected Horizon release; if those files are missing, preparation stops with an error.

## Using the result

Download the platform-matching native-build-linux-x86_64 or native-build-windows-x86_64 artifact and extract the horizon-client binary. On the computer where you use it, install and prepare a compatible Horizon release, then import the binary:

    horizon-launcher import-build <PATH-TO-horizon-client> --trust-unsigned

The launcher copies the installed base release's game files into the imported version and places the native binary there. Import the original Horizon instance ZIP separately through Horizon's instance import flow if you also need its worlds and settings.

## Targets

Linux x86_64 and Windows x86_64. macOS is deferred until its hosted build path is verified.

## Security

.hnmod contains native code and is not sandboxed. Build only mods whose source you have read and trust. The workflow uses ephemeral GitHub-hosted runners, read-only repository permissions and no persisted checkout credentials. An optional MINECRAFT_INPUTS_TOKEN is used only by the validation job to download a Release asset from a separate private input repository; it is not passed to the native build job.

## Experimental status

A successful run requires a prepared base and an actual native client binary; compiling the launcher CLI alone is not considered success. Check docs/STATUS.md for the remaining verification boundary.
