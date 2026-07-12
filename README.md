# Devbox

<img src="./misc/logo.svg" alt="Devbox logo" align="right" width="150" />

A ready-to-use Linux container for agent-driven development, with a launcher provided for efficient setup and interactions with the container.

- Ubuntu 26.04
- SDKMAN!
- Node.js
- OpenCode

## Install

[devbox](./bin/devbox) script is supported on Linux, MacOS and Windows.

### POSIX shells

```sh
curl -fsSL https://raw.githubusercontent.com/alexandru/devbox/main/install.sh | sh
```

### PowerShell

```powershell
irm https://raw.githubusercontent.com/alexandru/devbox/main/install.ps1 | iex
```

## Use

Requires Docker, Podman, or [wslc](https://learn.microsoft.com/en-us/windows/wsl/tutorials/wsl-containers?source=recommendations).

```sh
devbox start ~/Projects
devbox shell ~/Projects/path/to/project
```

For configuring the `devbox` script see the available env variables that it can use:

```sh
devbox help-env
```