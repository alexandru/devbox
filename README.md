# Devbox

A standalone helper and image for a JVM build-tools development container.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/alexandru/devbox/main/install.sh | sh && export PATH="$HOME/bin:$PATH"
```

```fish
curl -fsSL https://raw.githubusercontent.com/alexandru/devbox/main/install.sh | sh; and fish_add_path "$HOME/bin"
```

```powershell
irm https://raw.githubusercontent.com/alexandru/devbox/main/install.ps1 | iex
```

The installers require Python 3.9+. They use Homebrew, apt, dnf, yum, pacman,
apk, or zypper on POSIX, and winget, Chocolatey, or Scoop on Windows to install
it when needed. A sudo or UAC prompt may be required. Rerun an installer to
upgrade. POSIX installs to `~/bin`; Windows installs to
`%LOCALAPPDATA%\Programs\devbox\bin`; both persist that location in your PATH.

`devbox` is also used by another development-environment tool. The installers
refuse to overwrite or shadow another `devbox` command unless `DEVBOX_FORCE=1`
is explicitly set.

## Use

Install Docker, Podman, or `wslc` separately, then run:

```sh
devbox start /path/to/project
devbox shell
```

Use `devbox --help` for commands and `devbox help-env` for the canonical list
of `DEVBOX_*` image, volume, agent, OpenCode configuration, and authentication
variables. The breaking rename does not discover old containers or volumes.

The default image is
`ghcr.io/alexandru/devbox:latest`.

## Build and publish

```sh
make build-devbox
```

GitHub Actions publishes amd64 and arm64 images to GHCR weekly and on manual
dispatch, then creates the `latest` multi-platform manifest.
