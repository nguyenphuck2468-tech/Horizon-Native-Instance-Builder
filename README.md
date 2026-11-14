# Horizon Native Instance Builder

A GitHub Actions builder for Horizon native clients. It preserves the Horizon instance backup separately and obtains Minecraft game files directly from Mojang by default. Native mods are supplied as .hnmod bundles.

**Start here:** [Vietnamese usage guide](docs/HUONG-DAN.md).

## Inputs

    input/
      instance/
        instance.zip       # Horizon settings/worlds/instance backup
        horizon.zip        # accepted legacy filename
      minecraft/
        minecraft.zip      # optional override; normally downloaded from Mojang
      mods/
        mod-one.hnmod
        mod-two.hnmod

The Horizon instance ZIP is not a Minecraft installation. It is preserved byte-for-byte as a separate artifact and is never treated as the source of client JARs, libraries, or assets.

## Minecraft download

By default, each native-build runner downloads the selected official Minecraft version directly from Mojang:

- latest-release downloads the current release from Mojang's version manifest.
- latest-snapshot downloads the current snapshot.
- A concrete version such as 26.3 downloads that exact version when it exists in the official manifest.

The downloader obtains version metadata, client JARs, libraries (including declared classifier variants), asset indexes, and every referenced asset object. It verifies Mojang-provided sizes and SHA-1 hashes, rejects non-HTTPS/non-Mojang hosts and unsafe paths, and retries interrupted transfers. The game archive stays on the ephemeral runner and is not uploaded as a public workflow artifact.

An optional legacy path remains available: set minecraft_release_tag and the workflow will use a prebuilt full Minecraft game ZIP instead. Keep such an archive in a private repository; never publish Minecraft game files in a public Release.

## What the workflow builds

For Linux x86_64 and Windows x86_64, the workflow:

1. Validates the Horizon instance archive and trusted .hnmod bundles.
2. Downloads the selected Minecraft version from Mojang independently on each runner (or retrieves the optional private/prebuilt ZIP), then validates the client JAR, asset index and assets.
3. Checks out the selected revision of nguyenphuck2468-tech/horizon and builds its launcher CLI.
4. Installs the latest published Horizon base, prepares it from the downloaded Minecraft files, and invokes horizon-launcher native-build.
5. Publishes the actual horizon-client / horizon-client.exe binary, build logs and the original Horizon instance ZIP as separate artifacts.

The workflow does not sign in to a Microsoft/Minecraft account. Mojang's public version metadata and game-file endpoints are used; access to the game and compliance with the Minecraft EULA remain the user's responsibility.

## Run

Open Actions → Build Horizon Native Instance → Run workflow.

- horizon_revision: Horizon branch, tag or commit.
- minecraft_version: defaults to 26.3 to match Horizon main; choose another exact version only when it matches the selected Horizon revision's research-lock.json.
- minecraft_release_tag: leave blank for direct Mojang download. Only set this for the legacy prebuilt-ZIP path.
- instance_release_tag: optional Release tag for the Horizon instance backup.

## Import the result

Download the platform-matching native-build-linux-x86_64 or native-build-windows-x86_64 artifact and import its client binary:

    horizon-launcher import-build <PATH-TO-horizon-client> --trust-unsigned

Import the original Horizon instance ZIP separately if its worlds and settings are also needed.

## Targets and security

Linux x86_64 and Windows x86_64 are configured; macOS remains unverified. .hnmod bundles contain native code and are not sandboxed, so use only bundles whose source you trust. The workflow uses ephemeral GitHub-hosted runners, read-only repository permissions and no persisted checkout credentials. The downloaded Minecraft game files are not uploaded to Actions artifacts.

A successful compile is not yet proof of runtime compatibility. Check docs/STATUS.md and test the imported client on the target machine.
