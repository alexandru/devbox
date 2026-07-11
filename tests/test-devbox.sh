#!/usr/bin/env bash
set -euo pipefail

required_files=(
  .dockerignore
  Dockerfile
  Makefile
  README.md
  bin/devbox
  bin/devbox-entrypoint
  bin/osc52-clipboard
  .github/workflows/push.yml
)

for file in "${required_files[@]}"; do
  [[ -f "$file" ]] || { printf 'missing required file: %s\n' "$file" >&2; exit 1; }
done

for file in bin/devbox bin/devbox-entrypoint bin/osc52-clipboard; do
  [[ -x "$file" ]] || { printf 'not executable: %s\n' "$file" >&2; exit 1; }
done

bin/devbox --help >/dev/null
bin/devbox help-env >/dev/null

grep -Fq 'ghcr.io/alexandru/devbox' Makefile
grep -Fq 'ghcr.io/alexandru/devbox:latest' bin/devbox
grep -Fq 'push-devbox-manifest' Makefile
grep -Fq 'com.alexandru.devbox=true' bin/devbox
grep -Fq 'workflow_dispatch:' .github/workflows/push.yml
grep -Fq '0 0 * * 0' .github/workflows/push.yml
grep -Fq 'ubuntu-24.04-arm' .github/workflows/push.yml

old_name_prefix='dev'
old_name_suffix='container'
old_identifier_prefix='DEV'
old_identifier_suffix='CONTAINER_'

if grep -R --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=plans -n \
  --exclude='test-devbox.sh' \
  "${old_name_prefix}${old_name_suffix}\|${old_identifier_prefix}${old_identifier_suffix}" .; then
  printf 'stale previous project names found\n' >&2
  exit 1
fi
