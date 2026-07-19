#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
SOURCE="${REPO_ROOT}/docs/user-guide/GUIA_READING_SPACE_MATHMONGO.md"
OUTPUT="${REPO_ROOT}/docs/user-guide/GUIA_READING_SPACE_MATHMONGO.pdf"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

command -v python3 >/dev/null 2>&1 || fail "python3 is required for local-link validation."
command -v pandoc >/dev/null 2>&1 || fail "pandoc is required."

CHROME=""
for candidate in google-chrome chromium chromium-browser; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        CHROME="$(command -v "${candidate}")"
        break
    fi
done
[[ -n "${CHROME}" ]] || fail "Chrome or Chromium is required."
[[ -f "${SOURCE}" ]] || fail "Canonical source not found: ${SOURCE}"

python3 - "${SOURCE}" <<'PY'
from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

source = Path(sys.argv[1]).resolve()
text = source.read_text(encoding="utf-8")
base = source.parent

markdown_links = re.findall(r"(!?)\[[^\]]*\]\(([^)\n]+)\)", text)
html_links = [
    ("!" if tag.lower() == "img" else "", value)
    for tag, value in re.findall(
        r"<(img|a)\b[^>]*?\b(?:src|href)=[\"']([^\"']+)[\"']",
        text,
        flags=re.IGNORECASE,
    )
]

broken: list[str] = []
remote_images: list[str] = []
asset_count = 0
local_link_count = 0

for image_marker, raw_target in [*markdown_links, *html_links]:
    raw_target = raw_target.strip()
    if raw_target.startswith("<") and ">" in raw_target:
        target = raw_target[1 : raw_target.index(">")]
    else:
        try:
            parts = shlex.split(raw_target)
        except ValueError:
            parts = [raw_target]
        target = parts[0] if parts else ""

    parsed = urlsplit(target)
    if parsed.scheme in {"http", "https", "mailto", "data"} or target.startswith("//"):
        if image_marker and parsed.scheme in {"http", "https"}:
            remote_images.append(target)
        continue
    if not parsed.path:
        continue

    local_link_count += 1
    if image_marker:
        asset_count += 1
    path_text = unquote(parsed.path)
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = base / candidate
    if not candidate.exists():
        broken.append(f"{target} -> {candidate.resolve(strict=False)}")

if remote_images:
    print("Remote image assets are not allowed:", file=sys.stderr)
    for target in sorted(set(remote_images)):
        print(f"  - {target}", file=sys.stderr)
    raise SystemExit(1)

if broken:
    print("Broken local links or image references:", file=sys.stderr)
    for item in sorted(set(broken)):
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(1)

print(f"Validated {asset_count} local image references and {local_link_count} local links.")
PY

TEMP_DIR="$(mktemp -d /tmp/mathmongo-reading-guide-build.XXXXXX)"
cleanup() {
    local status=$?
    if [[ -n "${TEMP_DIR:-}" && -d "${TEMP_DIR}" && "${TEMP_DIR}" == /tmp/mathmongo-reading-guide-build.* ]]; then
        rm -rf -- "${TEMP_DIR}"
    fi
    exit "${status}"
}
trap cleanup EXIT INT TERM HUP

TEMP_HTML="${TEMP_DIR}/reading-space-guide.html"
TEMP_CSS="${TEMP_DIR}/reading-space-guide.css"
TEMP_PDF="${TEMP_DIR}/reading-space-guide.pdf"

cat >"${TEMP_CSS}" <<'CSS'
@page {
  size: A4;
  margin: 15mm 14mm 17mm;
}

:root {
  color-scheme: light;
  font-family: "Noto Sans", "Liberation Sans", Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.45;
  color: #172033;
}

body {
  max-width: none;
  margin: 0;
  background: #fff;
}

h1, h2, h3, h4 {
  color: #10264d;
  line-height: 1.2;
  page-break-after: avoid;
  break-after: avoid-page;
}

h1 { font-size: 25pt; margin: 0 0 1.2rem; }
h2 { font-size: 17pt; margin-top: 1.65rem; border-bottom: 1px solid #cad5e5; padding-bottom: .25rem; }
h3 { font-size: 13pt; margin-top: 1.25rem; }

p, li { orphans: 3; widows: 3; }
ul, ol { padding-left: 1.45rem; }
li + li { margin-top: .22rem; }

a { color: #1859a9; text-decoration: none; }

code {
  font-family: "Noto Sans Mono", "Liberation Mono", monospace;
  font-size: .9em;
  background: #eef2f7;
  padding: .08rem .24rem;
  border-radius: 3px;
  overflow-wrap: anywhere;
}

pre {
  background: #eef2f7;
  border: 1px solid #d4dce8;
  border-radius: 5px;
  padding: .65rem .8rem;
  white-space: pre-wrap;
  page-break-inside: avoid;
  break-inside: avoid-page;
}

blockquote {
  margin: .8rem 0;
  padding: .15rem .8rem;
  color: #34415a;
  border-left: 4px solid #4a83c7;
  background: #f3f7fc;
  page-break-inside: avoid;
  break-inside: avoid-page;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: .8rem 0;
  font-size: 9.2pt;
  page-break-inside: auto;
}

thead { display: table-header-group; }
tr { page-break-inside: avoid; break-inside: avoid-page; }
th, td { border: 1px solid #cbd4e0; padding: .36rem .42rem; vertical-align: top; }
th { background: #e9eff7; color: #10264d; }

figure {
  margin: 1rem 0 1.25rem;
  page-break-inside: avoid;
  break-inside: avoid-page;
}

figure img, p > img {
  display: block;
  max-width: 100%;
  max-height: 210mm;
  height: auto;
  margin: .5rem auto;
  border: 1px solid #aeb9c9;
  border-radius: 4px;
}

figcaption {
  margin-top: .4rem;
  color: #4d5a70;
  font-size: 9pt;
  text-align: left;
}

#TOC {
  page-break-after: always;
  break-after: page;
}

#TOC ul { list-style: none; padding-left: 1rem; }
#TOC > ul { padding-left: 0; }

.page-break {
  page-break-before: always;
  break-before: page;
}
CSS

pandoc "${SOURCE}" \
    --from=markdown+link_attributes \
    --to=html5 \
    --standalone \
    --self-contained \
    --resource-path="$(dirname -- "${SOURCE}")" \
    --toc \
    --toc-depth=2 \
    --metadata="pagetitle:Guía de Reading Space en MathMongo" \
    --css="${TEMP_CSS}" \
    --output="${TEMP_HTML}"

[[ -s "${TEMP_HTML}" ]] || fail "Pandoc did not produce a non-empty HTML file."

python3 - "${TEMP_HTML}" <<'PY'
from pathlib import Path
import sys

html_path = Path(sys.argv[1])
html = html_path.read_text(encoding="utf-8")
tag_base = (
    "https://github.com/EnriqueDiazO/math-knowledge-base/blob/"
    "v0.13.0-managed-source-workflow/docs/"
)
replacements = {
    "../MANAGED_SOURCE_WORKFLOW.md": tag_base + "MANAGED_SOURCE_WORKFLOW.md",
    "../RELEASE_NOTES_v0.13.0_MANAGED_SOURCE_WORKFLOW.md": (
        tag_base + "RELEASE_NOTES_v0.13.0_MANAGED_SOURCE_WORKFLOW.md"
    ),
    "../VERSION_CLOSURE_MANAGED_SOURCE_WORKFLOW.md": (
        tag_base + "VERSION_CLOSURE_MANAGED_SOURCE_WORKFLOW.md"
    ),
}
for local_target, published_target in replacements.items():
    marker = f'href="{local_target}"'
    if html.count(marker) != 1:
        raise SystemExit(
            f"Expected exactly one generated HTML link for {local_target}, "
            f"found {html.count(marker)}."
        )
    html = html.replace(marker, f'href="{published_target}"')
html_path.write_text(html, encoding="utf-8")
PY

"${CHROME}" \
    --headless=new \
    --disable-gpu \
    --disable-background-networking \
    --disable-component-update \
    --disable-default-apps \
    --disable-extensions \
    --disable-sync \
    --metrics-recording-only \
    --mute-audio \
    --no-default-browser-check \
    --no-first-run \
    --allow-file-access-from-files \
    --host-resolver-rules="MAP * 0.0.0.0" \
    --user-data-dir="${TEMP_DIR}/chrome-profile" \
    --no-pdf-header-footer \
    --print-to-pdf="${TEMP_PDF}" \
    "file://${TEMP_HTML}"

[[ -s "${TEMP_PDF}" ]] || fail "Chrome did not produce a non-empty PDF file."
head -c 5 "${TEMP_PDF}" | grep -q '^%PDF-' || fail "Chrome output is not a PDF."

source_device="$(stat -c '%d' "${TEMP_PDF}")"
output_device="$(stat -c '%d' "$(dirname -- "${OUTPUT}")")"
[[ "${source_device}" == "${output_device}" ]] || fail \
    "Safe atomic publication requires /tmp and the output directory to share a filesystem."

mv -f -- "${TEMP_PDF}" "${OUTPUT}"
printf 'Built %s from %s\n' "${OUTPUT}" "${SOURCE}"
