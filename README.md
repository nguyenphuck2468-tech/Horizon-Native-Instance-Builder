# Horizon Native Instance Builder

A forkable GitHub Actions project. The **instance input is a ZIP** (`instance.zip`); native mods are one or more `.hnmod` files.

## Input layout

```text
input/
  instance/
    instance.zip
  mods/
    mod-one.hnmod
    mod-two.hnmod
```

Fork this repository, put your exported Horizon instance ZIP at `input/instance/instance.zip`, and put trusted `.hnmod` files in `input/mods/`. Then run **Actions → Build Horizon Native Instance → Run workflow**.

For a large instance, publish `instance.zip` as a Release asset in this same repository and supply its tag in the workflow form. This avoids putting large world data in Git history.

## Important distinction

The instance ZIP and native runtime are separate deliverables. The builder preserves the ZIP unchanged; it does not stuff a game executable into the instance archive. Import the runtime with Horizon's `horizon-launcher import-build <PATH> --trust-unsigned`, then import the instance ZIP through the launcher's instance import flow. If the imported instance does not automatically select the custom native version, choose it in the instance's version settings.

## Targets

Linux x86_64 and Windows x86_64. macOS is deferred until its hosted build path is verified.

## Security

`.hnmod` contains native code and is not sandboxed. Build only mods you trust. The workflow uses ephemeral GitHub-hosted runners, read-only repository permissions, no secrets, and no persisted checkout credentials.

## Experimental status

The workflow includes a structural input validator and attempts to invoke Horizon's own `horizon-launcher native-build` command from a pinned Horizon checkout. A clean hosted runner may still need a prepared base Horizon installation for the native build command. The workflow preserves logs and reports this explicitly; a successful launcher compilation alone is not proof that a native runtime was generated. See `docs/STATUS.md`.
