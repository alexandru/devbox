#!/usr/bin/env bash
set -euo pipefail

required_files=(
  .dockerignore
  Dockerfile
  Makefile
  README.md
  bin/devcontainer
  bin/devcontainer-entrypoint
  bin/osc52-clipboard
  .github/workflows/push.yml
)

for file in "${required_files[@]}"; do
  [[ -f "$file" ]] || { printf 'missing required file: %s\n' "$file" >&2; exit 1; }
done

for file in bin/devcontainer bin/devcontainer-entrypoint bin/osc52-clipboard; do
  [[ -x "$file" ]] || { printf 'not executable: %s\n' "$file" >&2; exit 1; }
done

bin/devcontainer --help >/dev/null
bin/devcontainer help-env >/dev/null

grep -Fq 'ghcr.io/alexandru/devcontainer' Makefile
grep -Fq 'ghcr.io/alexandru/devcontainer:latest' bin/devcontainer
grep -Fq 'push-devcontainer-manifest' Makefile
grep -Fq 'com.alexandru.devcontainer=true' bin/devcontainer
grep -Fq 'workflow_dispatch:' .github/workflows/push.yml
grep -Fq '0 0 * * 0' .github/workflows/push.yml
grep -Fq 'ubuntu-24.04-arm' .github/workflows/push.yml

old_name_prefix='jdk-build-tools-'
old_name_suffix='devcontainer'
old_identifier_prefix='BUILD_TOOLS_'
old_identifier_suffix='DEV'
old_label_prefix='com.alexandru.docker-'
old_label_suffix='images.devcontainer'

if grep -R --exclude-dir=.git --exclude-dir=__pycache__ -n \
  "${old_name_prefix}${old_name_suffix}\|${old_identifier_prefix}${old_identifier_suffix}\|${old_label_prefix}${old_label_suffix}" .; then
  printf 'stale source-specific devcontainer names found\n' >&2
  exit 1
fi
