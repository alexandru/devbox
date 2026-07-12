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
# Starts the container, mounting ~/Projects in it
# (this being the "workspace" that contains projects of interest)
devbox start ~/Projects

# Opens a shell that chdirs straight in a desired project's path
devbox shell ~/Projects/path/to/project
```

For configuring the `devbox` script see the available env variables that it can use:

```sh
devbox help-env
```

For example, you can use 1Password CLI and supply secrets to `devbox` via a helper script like this:

```sh
#!/usr/bin/env bash

# Retrieving secrets from 1Password because keeping secrets in files is not OK
OP_BIN="$(which op)"
if [[ -z "$OP_BIN" ]]; then
  OP_BIN="$(which op.exe)"
fi
if [[ -z "$OP_BIN" ]]; then
  echo "1Password CLI (op) not found. Please install it and sign in."
  exit 1
fi

# What container CLI tools to use, valid choices are: wslc, podman, docker
# Forcing `podman`; if not provided, defaults to whatever it finds 
# (wslc, docker, podman in this order)
export CONTAINER_CLI="podman"

# Set the OpenCode Go API key for authentication
# (optional, OpenCode can be configured manually from a shell)
export DEVBOX_AUTH_OPENCODE_API_KEY="$("$OP_BIN" read op://Private/OpenCode/Api/Personal)"

# Set the Wireguard VPN configuration (optional, VPN is not required)
export DEVBOX_WIREGUARD_CONFIG_STR="$("$OP_BIN" read op://Private/VPN/notesPlain)"

exec devbox "$@"
```