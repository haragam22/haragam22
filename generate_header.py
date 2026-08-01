"""
Generates the profile header: typographic "dossier" card with animated
draw-in rules and rise/fade text. Static content (no GitHub data), so it's
a one-time render like generate_pinned_projects.py, not part of the daily
Action. CSS + SMIL both work fine here since this is referenced via <img
src="...">, not pasted inline into the README - GitHub only sanitizes
inline SVG/HTML, not linked image files.
"""

W, H = 1000, 320
BG = "#0d1117"
BONE = "#e6edf3"
RULE = "#30363d"
MUTED = "#8b949e"
DIM = "#6e7681"
ACCENT = "#79c0ff"

NAME = "Har Agam Deep Singh"
ROLE = "Machine Learning & Generative AI Developer."
FOCUS = "machine learning · generative ai · multi-agent systems · backend"
OPEN_LINE = "open to internships · research collaboration"
TAGS = ["MACHINE LEARNING", "GENERATIVE AI", "BACKEND"]
SCHOOL = "MAIT — 2028"

STYLE = f"""
.mono {{ font-family: ui-monospace, "SFMono-Regular", "SF Mono", Menlo, Consolas, "Liberation Mono", monospace; }}
.draw {{ stroke-dasharray: 1000; stroke-dashoffset: 1000; animation: draw 1.4s cubic-bezier(.6,0,.2,1) forwards; }}
@keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
.rise {{ opacity: 0; animation: rise .9s cubic-bezier(.2,.7,.2,1) forwards; }}
@keyframes rise {{ from {{ opacity:0; transform:translateY(12px); }} to {{ opacity:1; transform:translateY(0); }} }}
.fade {{ opacity: 0; animation: fade .7s ease forwards; }}
@keyframes fade {{ to {{ opacity: 1; }} }}
.a1{{animation-delay:.2s}} .a2{{animation-delay:.5s}} .a3{{animation-delay:.9s}} .a4{{animation-delay:1.2s}} .a5{{animation-delay:1.4s}} .a6{{animation-delay:1.7s}}
@media (prefers-reduced-motion: reduce) {{
  .draw,.rise,.fade {{ animation: none; }}
  .draw{{stroke-dashoffset:0}} .rise,.fade{{opacity:1}}
}}
"""


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg():
    parts = [
        f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="{_esc(NAME)} — {_esc(ROLE)}">',
        f'<style>{STYLE}</style>',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',

        f'<line class="draw a1" x1="48" y1="52" x2="{W-48}" y2="52" stroke="{RULE}" stroke-width="1"/>',
        '<g class="fade a1">',
        f'<text class="mono" fill="{MUTED}" x="48" y="38" font-size="11" letter-spacing="3.5">PORTFOLIO — INDEX № 001</text>',
        f'<text class="mono" fill="{MUTED}" x="{W-48}" y="38" font-size="11" letter-spacing="3.5" text-anchor="end">INDIA</text>',
        '</g>',

        '<g class="rise a2">',
        f'<text fill="{BONE}" class="mono" x="46" y="150" font-size="60" letter-spacing="-2">{_esc(NAME)}</text>',
        '</g>',
        '<g class="fade a3">',
        f'<text fill="{MUTED}" class="mono" x="48" y="184" font-size="17">{_esc(ROLE)}</text>',
        '</g>',

        '<g class="fade a4">',
        f'<text fill="{DIM}" class="mono" x="48" y="234" font-size="12.5" letter-spacing="1">focus  ▸</text>',
        f'<text fill="{ACCENT}" class="mono" x="128" y="234" font-size="12.5" letter-spacing="1">{_esc(FOCUS)}</text>',
        '</g>',
        '<g class="fade a5">',
        f'<text fill="{DIM}" class="mono" x="48" y="260" font-size="12.5" letter-spacing="1">{_esc(OPEN_LINE)}</text>',
        '</g>',

        f'<line class="draw a5" x1="48" y1="292" x2="{W-48}" y2="292" stroke="{RULE}" stroke-width="1"/>',
        '<g class="fade a6">',
    ]

    x = 48
    for i, tag in enumerate(TAGS):
        parts.append(f'<text fill="{MUTED}" class="mono" x="{x}" y="316" font-size="11.5" letter-spacing="3">{_esc(tag)}</text>')
        x += len(tag) * 8.6 + 24
        if i < len(TAGS) - 1:
            parts.append(f'<text fill="{ACCENT}" class="mono" x="{x-16}" y="316" font-size="11.5">·</text>')

    parts.append(f'<text fill="{MUTED}" class="mono" x="{W-48}" y="316" font-size="11.5" letter-spacing="3" text-anchor="end">{_esc(SCHOOL)}</text>')
    parts.append('</g>')
    parts.append('</svg>')
    return "\n".join(parts)


def main():
    with open("dist/header.svg", "w", encoding="utf-8") as f:
        f.write(build_svg())
    print("wrote dist/header.svg")


if __name__ == "__main__":
    main()
