"""
Generates the `> stack` panel: icon-only tiles (no labels), uniform size,
uniform monochrome accent, single source (simple-icons via cdn.simpleicons.org)
for every icon so nothing looks mismatched. Static content, one-time render
like generate_header.py / generate_pinned_projects.py - not part of the
daily Action.

Icons are fetched once and inlined as base64 data URIs. An SVG loaded via
<img> renders in a sandboxed "image context" that browsers block from
fetching further external resources, so a live https:// href inside a
generated SVG silently fails to render once it's embedded in the README.
"""
import base64
import requests

W = 760
BG = "#0d1117"
TITLE_COLOR = "#e6edf3"
LABEL_COLOR = "#8b949e"
TILE_FILL = "#161b22"
TILE_STROKE = "#30363d"
ACCENT = "58A6FF"  # no '#' - passed straight into the simpleicons URL

TILE, GAP = 52, 12
ICON = 26
ROW_LABEL_H = 26
ROW_GAP = 22
MARGIN = 4

CATEGORIES = [
    ("Core", ["python", "cplusplus"]),
    ("AI / ML", ["pytorch", "tensorflow", "scikitlearn", "opencv", "huggingface",
                 "kaggle", "keras", "numpy", "pandas"]),
    ("Backend & infra", ["fastapi", "django", "docker", "aws", "googlecloud",
                          "postgresql", "mongodb", "redis"]),
    ("Tools", ["git", "github", "githubactions"]),
]


# simple-icons has no Amazon/AWS logo (trademark removal) - only exception
# routed through skillicons.dev instead, everything else stays one source
_SKILLICONS_FALLBACK = {"aws"}


def _fetch_icon_data_uri(slug):
    if slug in _SKILLICONS_FALLBACK:
        url = f"https://skillicons.dev/icons?i={slug}"
    else:
        url = f"https://cdn.simpleicons.org/{slug}/{ACCENT}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    b64 = base64.b64encode(resp.content).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def build_svg():
    avail_w = W - 2 * MARGIN
    height = 20
    parts = []
    y = 20

    for label, icons in CATEGORIES:
        parts.append(
            f'<text x="{MARGIN}" y="{y}" font-family="monospace" font-size="12" '
            f'font-weight="700" letter-spacing="1" fill="{LABEL_COLOR}">{label.upper()}</text>'
        )
        y += ROW_LABEL_H

        per_row = max(1, (avail_w + GAP) // (TILE + GAP))
        for i, slug in enumerate(icons):
            col, row = i % per_row, i // per_row
            tx = MARGIN + col * (TILE + GAP)
            ty = y + row * (TILE + GAP)
            parts.append(
                f'<rect x="{tx}" y="{ty}" width="{TILE}" height="{TILE}" rx="12" '
                f'fill="{TILE_FILL}" stroke="{TILE_STROKE}" stroke-width="1.5"/>'
            )
            icon_xy = (TILE - ICON) / 2
            data_uri = _fetch_icon_data_uri(slug)
            parts.append(
                f'<image x="{tx+icon_xy:.1f}" y="{ty+icon_xy:.1f}" width="{ICON}" height="{ICON}" '
                f'href="{data_uri}"/>'
            )
        rows = -(-len(icons) // per_row)
        y += rows * TILE + (rows - 1) * GAP + ROW_GAP

    height = y - ROW_GAP + 8
    svg = (
        f'<svg width="100%" viewBox="0 0 {W} {height}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{W}" height="{height}" fill="{BG}"/>'
        + "".join(parts) +
        '</svg>'
    )
    return svg, height


def main():
    svg, height = build_svg()
    with open("dist/stack.svg", "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote dist/stack.svg ({W}x{height})")


if __name__ == "__main__":
    main()
