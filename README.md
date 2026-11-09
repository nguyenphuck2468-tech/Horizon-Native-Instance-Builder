# Horizon Native Instance Builder

A forkable GitHub Actions project. The instance input is a ZIP; native mods are one or more .hnmod files.

## Input layout

    input/
      instance/
        instance.zip   # preferred name
        horizon.zip    # legacy name, normalized by workflow
      mods/
        mod-one.hnmod
        mod-two.hnmod

Put a complete Minecraft game directory in input/instance/instance.zip (or horizon.zip). The archive must contain the official game-file layout, including versions/<version>/<version>.json; the workflow extracts it and passes that directory to Horizon's prepare --minecraft command. A Modrinth/CurseForge export containing only a manifest and overrides is not sufficient. The matching Minecraft files pinned by the selected Horizon release must be present, or preparation will stop rather than attempt an account sign-in on CI.

Put trusted .hnmod files in input/mods/. Then run Actions → Build Horizon Native Instance → Run workflow.

For a large instance, publish the ZIP as a Release asset in this same repository and supply its tag and asset filename in the workflow form. This avoids putting large world data in Git history. If a release tag is supplied, that release asset takes precedence and is copied to the canonical instance.zip input path.

## What the workflow builds

For Linux x86_64 and Windows x86_64, the workflow:

1. Validates ZIP paths, Minecraft version layout and each native-mod bundle.
2. Extracts the Minecraft files into a temporary runner directory.
3. Checks out the selected revision of nguyenphuck2468-tech/horizon and builds its launcher CLI.
4. Installs the latest published Horizon base, prepares it from the supplied Minecraft files, and invokes horizon-launcher native-build with the trusted .hnmod bundles.
5. Publishes the actual horizon-client / horizon-client.exe binary, build logs and the original instance ZIP as separate artifacts.

The instance ZIP is preserved byte-for-byte; it is not modified to contain the native executable.

## Using the result

Download the platform-matching native-build-linux-x86_64 or native-build-windows-x86_64 artifact and extract the horizon-client binary. On the computer where you use it, install and prepare a compatible Horizon release, then import the binary:

    horizon-launcher import-build <PATH-TO-horizon-client> --trust-unsigned

The launcher copies the installed base release's game files into the imported version and places the native binary there. Import the original instance ZIP separately through Horizon's instance import flow if you also need its worlds and settings.

## Targets

Linux x86_64 and Windows x86_64. macOS is deferred until its hosted build path is verified.

## Security

.hnmod contains native code and is not sandboxed. Build only mods whose source you have read and trust. The workflow uses ephemeral GitHub-hosted runners, read-only repository permissions, no secrets, and no persisted checkout credentials.

## Experimental status

A successful run now requires an actual prepared base and a native client binary; compiling the launcher CLI alone is not considered success. Check docs/STATUS.md for the remaining verification boundary.
