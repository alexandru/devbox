DEVCONTAINER_IMAGE := ghcr.io/alexandru/devcontainer
DEVCONTAINER_TAG := ${DEVCONTAINER_IMAGE}:latest
CONTAINER_CLI ?= $(shell command -v wslc.exe 2>/dev/null || command -v wslc 2>/dev/null || command -v docker 2>/dev/null || command -v podman 2>/dev/null)
PLATFORM ?= linux/amd64
PLATFORM_TAG = $(subst /,-,${PLATFORM})
DEVCONTAINER_PLATFORM_TAG = ${DEVCONTAINER_IMAGE}:${PLATFORM_TAG}

check-container-cli:
	@test -n "${CONTAINER_CLI}" || (echo "No container CLI found. Install wslc.exe, docker, or podman, or set CONTAINER_CLI=/path/to/cli." >&2; exit 1)

init-docker-buildx:
	docker buildx inspect mybuilder >/dev/null 2>&1 || docker buildx create --name mybuilder
	docker buildx use mybuilder

build-devcontainer: check-container-cli
	"${CONTAINER_CLI}" build -f ./Dockerfile -t "${DEVCONTAINER_TAG}" .

push-devcontainer: check-container-cli
	"${CONTAINER_CLI}" push "${DEVCONTAINER_TAG}"

build-devcontainer-platform: init-docker-buildx
	docker buildx build --platform "${PLATFORM}" -f ./Dockerfile -t "${DEVCONTAINER_PLATFORM_TAG}" ${DOCKER_EXTRA_ARGS} .

push-devcontainer-platform:
	DOCKER_EXTRA_ARGS="--push" $(MAKE) build-devcontainer-platform

push-devcontainer-manifest: init-docker-buildx
	docker buildx imagetools create -t "${DEVCONTAINER_TAG}" \
		"${DEVCONTAINER_IMAGE}:linux-amd64" \
		"${DEVCONTAINER_IMAGE}:linux-arm64"
