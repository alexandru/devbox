# Devbox

Container image meant for agent-driven development in a Linux environment.

## Image contents

- Ubuntu 26.04
- SDKMAN!
- Node.js 24
- OpenCode

## Install

### POSIX shells

```sh
curl -fsSL https://raw.githubusercontent.com/alexandru/devbox/main/install.sh | sh
```

### PowerShell

```powershell
irm https://raw.githubusercontent.com/alexandru/devbox/main/install.ps1 | iex
```

## Use

Requires Docker, Podman, or `wslc`.

```sh
devbox start /path/to/project
devbox shell
```

## Image

```text
ghcr.io/alexandru/devbox:latest
```
