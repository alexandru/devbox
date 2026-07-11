# Devbox

A ready-to-use Linux container for agent-driven development.

- Ubuntu 26.04
- SDKMAN!
- Node.js
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
devbox start ~/Projects
devbox shell ~/Projects/path/to/project
```
