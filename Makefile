DEVBOX_IMAGE := ghcr.io/alexandru/devbox
DEVBOX_TAG := ${DEVBOX_IMAGE}:latest
CONTAINER_CLI ?= $(shell command -v wslc.exe 2>/dev/null || command -v wslc 2>/dev/null || command -v docker 2>/dev/null || command -v podman 2>/dev/null)
PLATFORM ?= linux/amd64
PLATFORM_TAG = $(subst /,-,${PLATFORM})
DEVBOX_PLATFORM_TAG = ${DEVBOX_IMAGE}:${PLATFORM_TAG}

check-container-cli:
	@test -n "${CONTAINER_CLI}" || (echo "No container CLI found. Install wslc.exe, docker, or podman, or set CONTAINER_CLI=/path/to/cli." >&2; exit 1)

init-docker-buildx:
	docker buildx inspect mybuilder >/dev/null 2>&1 || docker buildx create --name mybuilder
	docker buildx use mybuilder

build-devbox: check-container-cli
	"${CONTAINER_CLI}" build -f ./Dockerfile -t "${DEVBOX_TAG}" .

push-devbox: check-container-cli
	"${CONTAINER_CLI}" push "${DEVBOX_TAG}"

build-devbox-platform: init-docker-buildx
	docker buildx build --platform "${PLATFORM}" -f ./Dockerfile -t "${DEVBOX_PLATFORM_TAG}" ${DOCKER_EXTRA_ARGS} .

push-devbox-platform:
	DOCKER_EXTRA_ARGS="--push" $(MAKE) build-devbox-platform

push-devbox-manifest: init-docker-buildx
	docker buildx imagetools create -t "${DEVBOX_TAG}" \
		"${DEVBOX_IMAGE}:linux-amd64" \
		"${DEVBOX_IMAGE}:linux-arm64"
