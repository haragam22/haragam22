"""
Generates a static SVG panel of numbered project cards for the
`> pinned.projects` README section. Static content, no daily regen -
same dark palette/monospace styling as generate_nn.py (not part of
the GitHub Actions pipeline, run manually when the project list changes).
"""
import textwrap

WIDTH = 760
BG = "#0d1117"
CARD_FILL = "#0d1117"
CARD_STROKE = "#30363d"
TITLE_COLOR = "#e6edf3"
ROLE_COLOR = "#8b949e"
DESC_COLOR = "#c9d1d9"
TAG_COLOR = "#6e7681"
INDEX_COLOR = "#21262d"
ACCENT = "#58a6ff"

COLS = 2
CARD_W = 364
CARD_H = 176
GAP = 24
PAD = 18
MARGIN = 16

PROJECTS = [
    ("debatemind", "backend & ML",
     "Autonomous AI debate framework, RL-optimized LLM reasoning backed "
     "by a real-time RAG pipeline for fact-checking",
     ["RL", "RAG", "LLMs"]),
    ("devlens", "backend lead",
     "AI codebase navigator: deterministic AST parsing + hybrid vector "
     "search mapping 500+ dependencies/issues; agentic backend explains "
     "architectural intent, cut onboarding time ~60%",
     ["Python", "AST", "vector search", "LLMs"]),
    ("jal-drishti", "ML lead",
     "Real-time underwater CV surveillance, YOLOv8 + FUnIE-GAN, 89%+ mAP "
     "across 5 threat classes; dual-mode backend with <80ms WebSocket telemetry",
     ["YOLOv8", "FUnIE-GAN", "WebSockets"]),
    ("sonic_script", "creator",
     'The White-Box Composer — a generative DSP engine where AI writes '
     "editable Python code to synthesize music instead of static audio "
     'files; self-correcting sandboxed codegen, validated by a CLAP-based '
     '"vibe check" against user intent',
     ["Python", "DSP", "Agentic AI", "Sandboxing"]),
    ("DATATHON-2026", "backend & architecture",
     "Catalyst by Zoho Datathon 2026 — conversational AI for the Karnataka "
     "State Police crime database, two-stage intent-verification "
     "architecture built to stay grounded and hallucination-resistant",
     ["Python", "LLM", "NLP", "Catalyst QuickML"]),
    ("galla-sathi", "backend & ML lead",
     "Vyapar-Vaani — voice-first AI copilot for kirana shopkeepers, built "
     "on a fine-tuned Gemma 4 model for a Kaggle Gemma hackathon (Track 1 "
     "— Vaani); manages ledger, inventory, and collections by voice across "
     "Hindi, Punjabi, and code-switched English",
     ["TypeScript", "Gemma", "Voice AI", "FastAPI"]),
]


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _wrap(text, width_chars, max_lines):
    lines = textwrap.wrap(text, width_chars)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "..."
    return lines


def build_card(x, y, index, name, role, desc, tags):
    parts = [
        f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="10" '
        f'fill="{CARD_FILL}" stroke="{CARD_STROKE}" stroke-width="1.5"/>',
        f'<text x="{x+PAD}" y="{y+40}" font-family="monospace" font-size="30" '
        f'font-weight="700" fill="{INDEX_COLOR}">{index:02d}</text>',
        f'<text x="{x+70}" y="{y+32}" font-family="monospace" font-size="16" '
        f'font-weight="700" fill="{TITLE_COLOR}">{_esc(name)}</text>',
        f'<text x="{x+70}" y="{y+48}" font-family="monospace" font-size="10.5" '
        f'fill="{ROLE_COLOR}">{_esc(role)}</text>',
    ]

    desc_lines = _wrap(desc, 46, 4)
    dy = y + 78
    for line in desc_lines:
        parts.append(
            f'<text x="{x+PAD}" y="{dy}" font-family="monospace" font-size="11.5" '
            f'fill="{DESC_COLOR}">{_esc(line)}</text>'
        )
        dy += 17

    tag_str = "  ·  ".join(tags)
    parts.append(
        f'<text x="{x+PAD}" y="{y+CARD_H-16}" font-family="monospace" font-size="9.5" '
        f'letter-spacing="0.5" fill="{TAG_COLOR}">{_esc(tag_str)}</text>'
    )
    return "".join(parts)


def build_svg():
    n = len(PROJECTS)
    rows = -(-n // COLS)
    height = MARGIN * 2 + rows * CARD_H + (rows - 1) * GAP

    parts = [
        f'<svg width="100%" viewBox="0 0 {WIDTH} {height}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="{WIDTH}" height="{height}" fill="{BG}"/>',
    ]

    for i, (name, role, desc, tags) in enumerate(PROJECTS):
        row, col = divmod(i, COLS)
        x = MARGIN + col * (CARD_W + GAP)
        y = MARGIN + row * (CARD_H + GAP)
        parts.append(build_card(x, y, i + 1, name, role, desc, tags))

    parts.append("</svg>")
    return "\n".join(parts), height


def main():
    svg, height = build_svg()
    with open("dist/pinned-projects.svg", "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote dist/pinned-projects.svg ({WIDTH}x{height})")


if __name__ == "__main__":
    main()
