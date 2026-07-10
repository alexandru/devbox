# Devcontainer

A standalone helper and image for a JVM build-tools development container.

## Use

Install Python 3 and Docker, Podman, or `wslc`, then run:

```sh
bin/devcontainer start /path/to/project
bin/devcontainer shell
```

Use `bin/devcontainer --help` for commands and `bin/devcontainer help-env` for
image, volume, agent, OpenCode configuration, and authentication environment
variables.

The default image is
`ghcr.io/alexandru/devcontainer:latest`.

## Build and publish

```sh
make build-devcontainer
```

GitHub Actions publishes amd64 and arm64 images to GHCR weekly and on manual
dispatch, then creates the `latest` multi-platform manifest.
