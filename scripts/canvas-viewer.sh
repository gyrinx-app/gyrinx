#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd "${script_dir}/.." && pwd)"
viewer_root="${repository_root}/tools/canvas-viewer"

if [[ ! -f "${viewer_root}/node_modules/.package-lock.json" ]] ||
    [[ "${viewer_root}/package-lock.json" -nt "${viewer_root}/node_modules/.package-lock.json" ]] ||
    [[ "${viewer_root}/package.json" -nt "${viewer_root}/node_modules/.package-lock.json" ]]; then
    npm --prefix "${viewer_root}" install
fi

exec npm --prefix "${viewer_root}" run dev
