"""
Generates an animated SVG: a neural network doing a visible forward pass.
A wave sweeps left to right, layer by layer; each node lights up to a
brightness proportional to its own random "weight" (so some nodes barely
glow, others flare) as the wave reaches it, then dims back down. A random
golden dust field twinkles in the background. At the end of each cycle the
output layer assembles into a colored mosaic, holds, fades, and loops.

All animation is native SVG SMIL (<animate>) - GitHub strips <script> tags
from README-embedded SVGs, so no JS is used anywhere.

Env vars required:
  GH_USERNAME - your GitHub username
  GH_PAT      - a classic personal access token with `read:user` scope
                (the default GITHUB_TOKEN in Actions cannot read your
                contribution calendar via the `viewer`/`user` GraphQL field)

If GH_PAT is missing or the API call fails, falls back to 0 contributions
(logs a warning) rather than crashing the workflow.
"""
import os
import random
import datetime
import requests

USERNAME = os.environ.get("GH_USERNAME", "")
TOKEN = os.environ.get("GH_PAT", "")

WIDTH, HEIGHT = 760, 320
BG = "#0d1117"
NODE_FILL = "#58a6ff"
EDGE = "#1f6feb"
EDGE_BASELINE = 0.18
LABEL_COLOR = "#8b949e"
DUST_COLOR = "#f4d03f"
MOSAIC_FILL = "#f5f5f5"
MOSAIC_STROKE = "#000000"

BASELINE, PEAK = 0.15, 1.0      # node opacity range; actual peak scaled by |weight|
LIGHT_DUR = 0.4                 # seconds a node/edge stays lit as the wave passes through

# time between adjacent layers lighting up (1/3 of the original 1.8s spacing)
LAYER_GAP = 0.6
MOSAIC_OFFSET = 90              # how far right of the output layer the picture assembles
MOSAIC_TILE_STAGGER = 0.15
MOSAIC_TILE_RISE = 0.1
MOSAIC_HOLD = 1.5
MOSAIC_FADE = 0.3
MOSAIC_TAIL = 0.3               # dark pause before the loop restarts

DUST_COUNT = 75
DUST_MIN_PERIOD, DUST_MAX_PERIOD = 3.0, 7.0


def _fetch_contribution_days():
    """Returns list of {date, contributionCount} dicts, oldest first, or [] on failure."""
    if not TOKEN or not USERNAME:
        print("warning: GH_PAT/GH_USERNAME not set, defaulting to empty calendar")
        return []
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }
    """
    try:
        resp = requests.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": {"login": USERNAME}},
            headers={"Authorization": f"bearer {TOKEN}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    except Exception as exc:
        print(f"warning: contribution lookup failed ({exc}), defaulting to empty calendar")
        return []
    days = [d for week in weeks for d in week["contributionDays"]]
    days.sort(key=lambda d: d["date"])
    return days


def get_todays_contributions():
    days = _fetch_contribution_days()
    today = datetime.date.today().isoformat()
    for day in days:
        if day["date"] == today:
            return day["contributionCount"]
    return 0


def get_current_streak():
    days = _fetch_contribution_days()
    if not days:
        return 0
    by_date = {d["date"]: d["contributionCount"] for d in days}
    streak = 0
    day = datetime.date.today()
    # today may not have a contribution yet and shouldn't break a streak that's
    # still "in progress" - only start counting misses from yesterday backward
    if by_date.get(day.isoformat(), 0) == 0:
        day -= datetime.timedelta(days=1)
    while by_date.get(day.isoformat(), 0) > 0:
        streak += 1
        day -= datetime.timedelta(days=1)
    return streak


def get_last_30_days_contributions():
    days = _fetch_contribution_days()
    return days[-30:]


def layer_sizes(commits):
    # input and output are fixed; hidden layers taper and grow with today's activity.
    boost = min(commits, 16) // 2
    hidden = [min(n + boost, 9) for n in (5, 4, 3)]
    return [6, *hidden, 6]


def build_dust():
    parts = [f'<g fill="{DUST_COLOR}">']
    for _ in range(DUST_COUNT):
        x = random.uniform(0, WIDTH)
        y = random.uniform(0, HEIGHT)
        r = random.uniform(0.6, 1.6)
        period = random.uniform(DUST_MIN_PERIOD, DUST_MAX_PERIOD)
        phase = random.uniform(0, DUST_MAX_PERIOD)
        peak = random.uniform(0.4, 0.9)
        # gentle random drift: wander through a few nearby points and loop back to start
        drift = random.uniform(12, 30)
        move_dur = random.uniform(6.0, 12.0)
        pts = [(0.0, 0.0)]
        for _ in range(3):
            pts.append((random.uniform(-drift, drift), random.uniform(-drift, drift)))
        pts.append((0.0, 0.0))
        path_d = "M " + " L ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" opacity="0.05">'
            f'<animate attributeName="opacity" values="0.05;{peak:.2f};0.05" '
            f'keyTimes="0;0.5;1" dur="{period:.2f}s" begin="{phase:.2f}s" repeatCount="indefinite"/>'
            f'<animateMotion path="{path_d}" dur="{move_dur:.2f}s" begin="{phase:.2f}s" '
            f'calcMode="linear" repeatCount="indefinite"/>'
            f'</circle>'
        )
    parts.append("</g>")
    return "".join(parts)


def build_svg(sizes):
    n_layers = len(sizes)
    margin_x, margin_y = 70, 50
    right_margin = margin_x + MOSAIC_OFFSET
    usable_w = WIDTH - margin_x - right_margin
    xs = [margin_x + usable_w * i / (n_layers - 1) for i in range(n_layers)]

    nodes = []
    for li, count in enumerate(sizes):
        gap = (HEIGHT - 2 * margin_y) / (count + 1)
        for i in range(count):
            y = margin_y + gap * (i + 1)
            nodes.append({"x": xs[li], "y": y, "layer": li, "weight": random.uniform(-0.99, 0.99)})

    travel_end = LAYER_GAP * (n_layers - 1)

    def arrive_time(li):
        return LAYER_GAP * li

    # mosaic timing derives from when the wave reaches the output layer
    mosaic_start = travel_end
    mosaic_appear_end = mosaic_start + 5 * MOSAIC_TILE_STAGGER + MOSAIC_TILE_RISE
    mosaic_hold_end = mosaic_appear_end + MOSAIC_HOLD
    mosaic_fade_end = mosaic_hold_end + MOSAIC_FADE
    cycle = mosaic_fade_end + MOSAIC_TAIL

    parts = [
        f'<svg width="100%" viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{BG}"/>',
        build_dust(),
    ]

    # edges: faint by default, glow as the wave crosses from source to target node
    parts.append(f'<g stroke="{EDGE}" stroke-width="0.6" fill="none">')
    for li in range(n_layers - 1):
        layer_a = [n for n in nodes if n["layer"] == li]
        layer_b = [n for n in nodes if n["layer"] == li + 1]
        t_a, t_b = arrive_time(li), arrive_time(li + 1)
        t_peak = (t_a + t_b) / 2
        for a in layer_a:
            for b in sorted(layer_b, key=lambda b: abs(b["y"] - a["y"]))[:2]:
                strength = max(abs(a["weight"]), abs(b["weight"]))
                peak_opacity = EDGE_BASELINE + (0.85 - EDGE_BASELINE) * strength
                key_times = sorted({0.0, round(t_a / cycle, 4), round(t_peak / cycle, 4), round(t_b / cycle, 4), 1.0})
                shape_by_kt = {
                    0.0: EDGE_BASELINE, round(t_a / cycle, 4): EDGE_BASELINE,
                    round(t_peak / cycle, 4): peak_opacity, round(t_b / cycle, 4): EDGE_BASELINE, 1.0: EDGE_BASELINE,
                }
                values, last = [], EDGE_BASELINE
                for kt in key_times:
                    if kt in shape_by_kt:
                        last = shape_by_kt[kt]
                    values.append(round(last, 3))
                anim = (
                    f'<animate attributeName="stroke-opacity" values="{";".join(str(v) for v in values)}" '
                    f'keyTimes="{";".join(str(k) for k in key_times)}" dur="{cycle:.3f}s" repeatCount="indefinite"/>'
                )
                parts.append(
                    f'<line x1="{a["x"]:.1f}" y1="{a["y"]:.1f}" x2="{b["x"]:.1f}" y2="{b["y"]:.1f}" '
                    f'stroke-opacity="{EDGE_BASELINE}">{anim}</line>'
                )
    parts.append("</g>")

    # forward-pass nodes: wave sweeps layer by layer, each node lights to a
    # brightness proportional to |weight|, then dims back down
    for n in nodes:
        t_arrive = arrive_time(n["layer"])
        t_peak = t_arrive + LIGHT_DUR / 2
        t_end = t_arrive + LIGHT_DUR
        peak_opacity = BASELINE + (PEAK - BASELINE) * abs(n["weight"])
        key_times = sorted({0.0, round(t_arrive / cycle, 4), round(t_peak / cycle, 4), round(t_end / cycle, 4), 1.0})
        shape_by_kt = {
            0.0: BASELINE,
            round(t_arrive / cycle, 4): BASELINE,
            round(t_peak / cycle, 4): peak_opacity,
            round(t_end / cycle, 4): BASELINE,
            1.0: BASELINE,
        }
        values = []
        last = BASELINE
        for kt in key_times:
            if kt in shape_by_kt:
                last = shape_by_kt[kt]
            values.append(round(last, 3))
        values_str = ";".join(str(v) for v in values)
        kt_str = ";".join(str(k) for k in key_times)
        anim = (
            f'<animate attributeName="opacity" values="{values_str}" keyTimes="{kt_str}" '
            f'dur="{cycle:.3f}s" repeatCount="indefinite"/>'
        )
        parts.append(f'<circle cx="{n["x"]:.1f}" cy="{n["y"]:.1f}" r="8" fill="{NODE_FILL}" opacity="{BASELINE}">{anim}</circle>')
        sign = "+" if n["weight"] >= 0 else ""
        parts.append(
            f'<text x="{n["x"]+7:.1f}" y="{n["y"]-9:.1f}" font-family="monospace" font-size="6.5" '
            f'fill="{LABEL_COLOR}" opacity="{BASELINE}">{sign}{n["weight"]:.2f}{anim}</text>'
        )

    # output picture finale: a 3x2 white/black-grid picture assembles just to the
    # right of the output layer once the wave arrives, each square sliding in
    # from the right, holds, fades, and the whole loop restarts
    out_x = xs[-1]
    out_y = HEIGHT / 2
    pic_cx = out_x + MOSAIC_OFFSET
    tile_w, tile_h = 22, 18
    grid_w, grid_h = 3 * tile_w, 2 * tile_h
    top_left_x = pic_cx - grid_w / 2
    top_left_y = out_y - grid_h / 2
    slide_dx = 26

    parts.append('<g>')
    for i in range(6):
        row, col = divmod(i, 3)
        tx = top_left_x + col * tile_w
        ty = top_left_y + row * tile_h
        appear = mosaic_start + i * MOSAIC_TILE_STAGGER
        rise_end = appear + MOSAIC_TILE_RISE
        key_times = sorted({
            0.0,
            round(appear / cycle, 4),
            round(rise_end / cycle, 4),
            round(mosaic_hold_end / cycle, 4),
            round(mosaic_fade_end / cycle, 4),
            1.0,
        })
        shape_by_kt = {0.0: 0, round(rise_end / cycle, 4): 1, round(mosaic_hold_end / cycle, 4): 1,
                       round(mosaic_fade_end / cycle, 4): 0, 1.0: 0}
        values, last = [], 0
        for kt in key_times:
            if kt in shape_by_kt:
                last = shape_by_kt[kt]
            values.append(last)
        opacity_anim = (
            f'<animate attributeName="opacity" values="{";".join(str(v) for v in values)}" '
            f'keyTimes="{";".join(str(k) for k in key_times)}" dur="{cycle:.3f}s" repeatCount="indefinite"/>'
        )
        slide_kt = sorted({0.0, round(appear / cycle, 4), round(rise_end / cycle, 4), 1.0})
        slide_shape = {0.0: slide_dx, round(appear / cycle, 4): slide_dx, round(rise_end / cycle, 4): 0, 1.0: 0}
        slide_values, last_v = [], slide_dx
        for kt in slide_kt:
            if kt in slide_shape:
                last_v = slide_shape[kt]
            slide_values.append(last_v)
        slide_anim = (
            f'<animateTransform attributeName="transform" type="translate" '
            f'values="{";".join(f"{v},0" for v in slide_values)}" '
            f'keyTimes="{";".join(str(k) for k in slide_kt)}" dur="{cycle:.3f}s" repeatCount="indefinite"/>'
        )
        parts.append(
            f'<rect x="{tx:.1f}" y="{ty:.1f}" width="{tile_w}" height="{tile_h}" '
            f'fill="{MOSAIC_FILL}" stroke="{MOSAIC_STROKE}" stroke-width="1" opacity="0">'
            f'{opacity_anim}{slide_anim}</rect>'
        )
    parts.append('</g>')

    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Telemetry: 30-day contribution chart
# ---------------------------------------------------------------------------

def build_contribution_chart(days):
    if not days:
        today = datetime.date.today()
        days = [{"date": (today - datetime.timedelta(days=29 - i)).isoformat(), "contributionCount": 0} for i in range(30)]
    w, h = 760, 240
    pad_l, pad_r, pad_t, pad_b = 40, 20, 40, 30
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b
    counts = [d["contributionCount"] for d in days] or [0]
    max_c = max(max(counts), 1)

    n = len(days)
    xs = [pad_l + (plot_w * i / max(n - 1, 1)) for i in range(n)]
    ys = [pad_t + plot_h - (plot_h * c / max_c) for c in counts]

    line_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area_pts = f"{xs[0]:.1f},{pad_t+plot_h:.1f} " + line_pts + f" {xs[-1]:.1f},{pad_t+plot_h:.1f}"

    parts = [
        f'<svg width="100%" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="{w}" height="{h}" fill="{BG}"/>',
        f'<text x="{pad_l}" y="24" font-family="monospace" font-size="13" letter-spacing="2" '
        f'fill="#e6edf3">CONTRIBUTION TELEMETRY</text>',
    ]

    # gridlines: 4 horizontal
    for i in range(5):
        gy = pad_t + plot_h * i / 4
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-pad_r}" y2="{gy:.1f}" stroke="#21262d" stroke-width="1"/>')
        val = round(max_c * (4 - i) / 4)
        parts.append(f'<text x="{pad_l-8}" y="{gy+3:.1f}" font-family="monospace" font-size="8" fill="{LABEL_COLOR}" text-anchor="end">{val}</text>')

    # x-axis day-of-month labels, sparse to avoid crowding
    step = max(n // 8, 1)
    for i, d in enumerate(days):
        if i % step != 0 and i != n - 1:
            continue
        day_num = int(d["date"].split("-")[-1])
        parts.append(f'<text x="{xs[i]:.1f}" y="{h-8}" font-family="monospace" font-size="8" fill="{LABEL_COLOR}" text-anchor="middle">{day_num}</text>')

    parts.append(f'<polygon points="{area_pts}" fill="#58a6ff" fill-opacity="0.12"/>')
    parts.append(f'<polyline points="{line_pts}" fill="none" stroke="#e6edf3" stroke-width="1.5"/>')
    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Telemetry: core repo/language panel
# ---------------------------------------------------------------------------

def _fetch_user_repos():
    if not TOKEN or not USERNAME:
        print("warning: GH_PAT/GH_USERNAME not set, defaulting to empty repo list")
        return []
    repos, page = [], 1
    try:
        while True:
            resp = requests.get(
                f"https://api.github.com/users/{USERNAME}/repos",
                params={"per_page": 100, "page": page},
                headers={"Authorization": f"token {TOKEN}"},
                timeout=30,
            )
            resp.raise_for_status()
            batch = resp.json()
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    except Exception as exc:
        print(f"warning: repo list lookup failed ({exc}), defaulting to empty list")
        return []
    return repos


def _fetch_last_commit_date(repos):
    # ponytail: checks only the most-recently-pushed repo, not every repo's commit history
    if not repos:
        return None
    latest_repo = max(repos, key=lambda r: r.get("pushed_at") or "")
    pushed_at = latest_repo.get("pushed_at")
    return pushed_at


# crude heuristic: majority language across repos maps to a domain label.
# genuinely fuzzy - good enough for a vibe, not a resume claim.
_DOMAIN_MAP = {
    "Python": "Machine Learning & Backend",
    "Jupyter Notebook": "Machine Learning & Data Science",
    "JavaScript": "Web & Frontend",
    "TypeScript": "Web & Frontend",
    "Go": "Systems & Backend",
    "Rust": "Systems Programming",
    "C++": "Systems Programming",
    "C": "Systems Programming",
    "Java": "Backend & Enterprise",
    "C#": "Backend & Tools",
    "HTML": "Web & Frontend",
    "Swift": "Mobile Development",
    "Kotlin": "Mobile Development",
    "Shell": "Tooling & DevOps",
}


def _language_breakdown(repos):
    counts = {}
    for r in repos:
        lang = r.get("language")
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    total = sum(counts.values()) or 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [(lang, cnt / total) for lang, cnt in ranked], ranked


def build_core_telemetry(repos):
    w, h = 760, 220
    parts = [
        f'<svg width="100%" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="{w}" height="{h}" fill="{BG}"/>',
        f'<text x="20" y="28" font-family="monospace" font-size="13" letter-spacing="2" fill="#e6edf3">GITHUB CORE TELEMETRY</text>',
        f'<line x1="{w/2:.0f}" y1="45" x2="{w/2:.0f}" y2="{h-15}" stroke="#21262d" stroke-width="1"/>',
    ]

    breakdown, ranked = _language_breakdown(repos)
    primary_domain = _DOMAIN_MAP.get(ranked[0][0], ranked[0][0]) if ranked else "Exploring"

    last_push = _fetch_last_commit_date(repos)
    active = False
    if last_push:
        pushed = datetime.datetime.strptime(last_push, "%Y-%m-%dT%H:%M:%SZ").date()
        active = (datetime.date.today() - pushed).days <= 14
    commit_status = "Active Contributor" if active else "Between Commits"

    left_fields = [
        ("Total Repositories", str(len(repos))),
        ("Primary Domain", primary_domain),
        ("Commit Status", commit_status),
        ("Profile Handle", f"@{USERNAME}" if USERNAME else "unknown"),
    ]
    ly = 65
    for label, value in left_fields:
        parts.append(f'<text x="20" y="{ly}" font-family="monospace" font-size="9" fill="{LABEL_COLOR}">{_esc(label)}</text>')
        parts.append(f'<text x="20" y="{ly+16}" font-family="monospace" font-size="12" fill="#e6edf3">{_esc(value)}</text>')
        ly += 40

    rx = w / 2 + 30
    ry = 65
    bar_w_max = w - rx - 90
    for lang, frac in breakdown[:4]:
        pct = round(frac * 100)
        parts.append(f'<text x="{rx:.0f}" y="{ry}" font-family="monospace" font-size="10" fill="#e6edf3">{_esc(lang)}</text>')
        bar_y = ry + 6
        parts.append(f'<rect x="{rx:.0f}" y="{bar_y}" width="{bar_w_max}" height="6" fill="#21262d" rx="3"/>')
        parts.append(f'<rect x="{rx:.0f}" y="{bar_y}" width="{bar_w_max*frac:.1f}" height="6" fill="#58a6ff" rx="3"/>')
        parts.append(f'<text x="{rx+bar_w_max+8:.0f}" y="{bar_y+6}" font-family="monospace" font-size="9" fill="{LABEL_COLOR}">{pct}%</text>')
        ry += 30

    parts.append("</svg>")
    return "\n".join(parts)


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Flat 2D pixel-art rocket scene: assembles from streak length, fuels,
# launches, resets, loops. Native SMIL only (no <script>, same GitHub-README
# constraint as everything else in this file). Front-on sprite style, not
# isometric - stepped rectangles with black outlines, sitting in a full sky
# + ground scene rather than a bare dark background.
# ---------------------------------------------------------------------------

# streak -> pieces assembled mapping: one piece per streak day, capped at 6
# (engine, lower body, upper body/stripe, nose, fins, nose cap). streak 0 or 1
# day -> empty pad. streak >= 6 -> fully built. tune ROCKET_PIECE_CAP to
# change how many days it takes to "complete" the rocket.
ROCKET_PIECE_CAP = 6

SKY_TOP = "#0b1e3d"
SKY_HORIZON = "#5b7fb0"
OUTLINE = "#12100b"
STAR_COLOR = "#f5f6fa"
CLOUD_COLOR = "#eef1f5"
CLOUD_SHADE = "#c9d1d9"
DIRT_COLOR = "#8a5a34"
DIRT_EDGE = "#5e3b20"
GRASS_COLOR = "#4c9a4a"
GRASS_DARK = "#357536"
ROCK_COLOR = "#7c8591"
ROCKET_WHITE = "#f2f2ec"
ROCKET_RED = "#d1453b"
ROCKET_BLUE = "#3f7fd1"
ROCKET_DARK = "#3a3a3a"
FLAME_A = "#ffd23f"
FLAME_B = "#ff6b35"
SMOKE_COLOR = "#d8d8d8"


def pieces_for_streak(streak):
    return max(0, min(streak, ROCKET_PIECE_CAP))


def _stepped_anim(attr, cycle, breakpoints, tag="animate", extra=""):
    """breakpoints: sorted [(t_seconds, value_str), ...]. Holds each value from
    its breakpoint until the next one, wraps at the cycle boundary - same
    step-animation technique used elsewhere in this file (see build_svg)."""
    key_times = sorted({0.0, *(round(t / cycle, 4) for t, _ in breakpoints), 1.0})
    shape = {round(t / cycle, 4): v for t, v in breakpoints}
    values, last = [], breakpoints[0][1]
    for kt in key_times:
        if kt in shape:
            last = shape[kt]
        values.append(last)
    vs = ";".join(values)
    kts = ";".join(str(k) for k in key_times)
    return (
        f'<{tag} attributeName="{attr}" values="{vs}" keyTimes="{kts}" '
        f'dur="{cycle:.3f}s" repeatCount="indefinite" {extra}/>'
    )


def _outlined_rect(x, y, w, h, fill, sw=2):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{OUTLINE}" stroke-width="{sw}"/>'


def _outlined_poly(points, fill, sw=2):
    return f'<polygon points="{points}" fill="{fill}" stroke="{OUTLINE}" stroke-width="{sw}" stroke-linejoin="round"/>'


def _build_cloud(cx, cy, scale=1.0):
    puffs = [(-18, 6, 16, 10), (-4, 0, 20, 13), (14, 6, 15, 10), (0, 10, 30, 8)]
    parts = []
    for dx, dy, pw, ph in puffs:
        x, y = cx + dx * scale, cy + dy * scale
        parts.append(_outlined_rect(x, y, pw * scale, ph * scale, CLOUD_COLOR))
    # small shaded underside for a bit of depth without breaking the flat look
    parts.append(f'<rect x="{cx-14*scale:.1f}" y="{cy+12*scale:.1f}" width="{30*scale:.1f}" height="4" fill="{CLOUD_SHADE}"/>')
    return "".join(parts)


def build_rocket(streak):
    n_pieces = pieces_for_streak(streak)

    w, h = 800, 450
    cycle = 14.0
    # assembly -> ignite/ascend -> hold offscreen -> end card -> reset
    t_assembly_end = cycle * 0.35
    t_ignite = t_assembly_end + 0.3
    t_launch_end = cycle * 0.72       # rocket fully clear of the canvas by here
    t_endcard_start = t_launch_end + 0.3
    t_endcard_end = cycle * 0.93
    # reset phase fills the remainder of the cycle back to 1.0

    ground_y = 380
    pad_x = w / 2  # dead center

    parts = [
        f'<svg width="100%" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges">',
        '<defs>',
        f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{SKY_TOP}"/><stop offset="100%" stop-color="{SKY_HORIZON}"/></linearGradient>',
        '</defs>',
        f'<rect width="{w}" height="{h}" fill="url(#sky)"/>',
    ]

    # stars: independent async twinkle, same per-element random-phase pulse
    # technique as the firefly dust field in build_dust()
    for _ in range(26):
        sx, sy = random.uniform(10, w - 10), random.uniform(14, 190)
        period = random.uniform(1.8, 4.0)
        phase = random.uniform(0, period)
        peak = random.uniform(0.6, 1.0)
        s = random.choice([2, 2, 3])
        parts.append(
            f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{s}" height="{s}" fill="{STAR_COLOR}" opacity="0.15">'
            f'<animate attributeName="opacity" values="0.15;{peak:.2f};0.15" keyTimes="0;0.5;1" '
            f'dur="{period:.2f}s" begin="{phase:.2f}s" repeatCount="indefinite"/></rect>'
        )

    # drifting clouds, slow sideways loop, spread across the wider canvas
    for i, (cy, scale, dur, delay) in enumerate([
        (60, 1.0, 34, 0), (110, 0.7, 42, -14), (40, 0.55, 38, -26), (150, 0.8, 46, -6),
    ]):
        drift = f'<animateTransform attributeName="transform" type="translate" ' \
                f'values="-60,0;{w+60},0" dur="{dur}s" begin="{delay}s" repeatCount="indefinite"/>'
        parts.append(f'<g>{_build_cloud(0, cy, scale)}{drift}</g>')

    # ground: dirt band with a darker seam, grass strip on top
    parts.append(f'<rect x="0" y="{ground_y}" width="{w}" height="{h-ground_y}" fill="{DIRT_COLOR}"/>')
    parts.append(f'<rect x="0" y="{ground_y}" width="{w}" height="4" fill="{DIRT_EDGE}"/>')
    parts.append(f'<rect x="0" y="{ground_y-8}" width="{w}" height="8" fill="{GRASS_COLOR}"/>')
    parts.append(f'<rect x="0" y="{ground_y-8}" width="{w}" height="3" fill="{GRASS_DARK}"/>')

    # ground texture: a scattering of rocks and grass tufts across the full width
    for gx in (30, 90, 200, 620, 700, 760):
        parts.append(_outlined_rect(gx, ground_y + 14, 12, 8, ROCK_COLOR, sw=1.5))
    for gx in (55, 140, 240, 520, 640, 730):
        parts.append(
            f'<g stroke="{GRASS_DARK}" stroke-width="2">'
            f'<line x1="{gx}" y1="{ground_y-6}" x2="{gx-3}" y2="{ground_y-16}"/>'
            f'<line x1="{gx+4}" y1="{ground_y-6}" x2="{gx+4}" y2="{ground_y-18}"/>'
            f'<line x1="{gx+8}" y1="{ground_y-6}" x2="{gx+11}" y2="{ground_y-16}"/>'
            f'</g>'
        )

    # -- rocket, built from flat blocky sprite pieces, stacked bottom-up --
    # each *_y is the piece's top edge; heights below must match the shapes
    # each builder actually draws so pieces sit flush with no gaps/overlaps
    body_w = 46
    engine_h, lower_h, upper_h, nose_h, cap_h = 34, 46, 60, 42, 26
    engine_y = ground_y - engine_h
    lower_y = engine_y - lower_h
    upper_y = lower_y - upper_h
    nose_y = upper_y - nose_h
    cap_y = nose_y - cap_h

    def piece_engine():
        y = engine_y
        return (
            _outlined_rect(pad_x - body_w/2, y, body_w, 34, ROCKET_DARK)
            + _outlined_poly(f"{pad_x-body_w/2-10},{y+34} {pad_x-body_w/2+10},{y+34} {pad_x-body_w/2+2},{y+8}", ROCKET_RED)
            + _outlined_poly(f"{pad_x+body_w/2+10},{y+34} {pad_x+body_w/2-10},{y+34} {pad_x+body_w/2-2},{y+8}", ROCKET_RED)
        )

    def piece_lower_body():
        y = lower_y
        return _outlined_rect(pad_x - body_w/2, y, body_w, 46, ROCKET_WHITE) + \
            _outlined_rect(pad_x - body_w/2, y + 16, body_w, 10, ROCKET_BLUE)

    def piece_upper_body():
        y = upper_y
        return _outlined_rect(pad_x - body_w/2, y, body_w, 60, ROCKET_WHITE) + \
            _outlined_rect(pad_x - body_w/2, y + 8, body_w, 8, ROCKET_RED) + \
            f'<circle cx="{pad_x}" cy="{y+34}" r="12" fill="{SKY_TOP}" stroke="{OUTLINE}" stroke-width="2"/>'

    def piece_nose():
        y = nose_y
        # stepped-triangle taper: 3 shrinking bands instead of a smooth curve
        steps = [(body_w, 16), (body_w*0.62, 14), (body_w*0.3, 12)]
        segs, sy = [], y + 42
        for sw_, sh in steps:
            segs.append(_outlined_rect(pad_x - sw_/2, sy - sh, sw_, sh, ROCKET_RED))
            sy -= sh
        return "".join(segs)

    def piece_cap():
        y = cap_y
        return _outlined_poly(f"{pad_x-6},{y+26} {pad_x+6},{y+26} {pad_x},{y}", ROCKET_WHITE)

    piece_defs = [
        ("engine", piece_engine),
        ("lower body", piece_lower_body),
        ("upper body", piece_upper_body),
        ("nose", piece_nose),
        ("fins", None),  # rendered with the engine block above, counts as a build step
        ("cap", piece_cap),
    ]

    rocket_children = []
    for i, (name, builder) in enumerate(piece_defs):
        if i >= n_pieces or builder is None:
            continue
        appear_t = (i + 1) * (t_assembly_end / (ROCKET_PIECE_CAP + 1))
        drop_dy = -80
        translate_anim = _stepped_anim(
            "transform", cycle,
            [(0.0, f"translate(0,{drop_dy})"), (appear_t, f"translate(0,{drop_dy})"), (appear_t + 0.35, "translate(0,0)")],
            tag="animateTransform", extra='type="translate"',
        )
        opacity_anim = _stepped_anim("opacity", cycle, [(0.0, "0"), (appear_t, "0"), (appear_t + 0.01, "1")])
        rocket_children.append(f'<g opacity="0">{opacity_anim}<g>{translate_anim}{builder()}</g></g>')

    # engine flame: attached to the rocket group so it climbs with it, visible
    # and flickering for the whole ascent (not just the ignition instant)
    flame_visible_anim = _stepped_anim(
        "opacity", cycle,
        [(0.0, "0"), (t_ignite, "0"), (t_ignite + 0.05, "1"), (t_launch_end, "1"), (t_launch_end + 0.15, "0")],
    )
    flicker_b = '<animate attributeName="opacity" values="1;0.55;0.9;0.7;1" dur="0.3s" repeatCount="indefinite"/>'
    flicker_a = '<animate attributeName="opacity" values="0.85;1;0.6;1;0.85" dur="0.22s" repeatCount="indefinite"/>'
    flame_group = (
        f'<g opacity="0">{flame_visible_anim}'
        f'<polygon points="{pad_x-14},{ground_y-2} {pad_x+14},{ground_y-2} {pad_x},{ground_y+36}" '
        f'fill="{FLAME_B}" stroke="{OUTLINE}" stroke-width="2" stroke-linejoin="round">{flicker_b}</polygon>'
        f'<polygon points="{pad_x-7},{ground_y-2} {pad_x+7},{ground_y-2} {pad_x},{ground_y+20}" '
        f'fill="{FLAME_A}" stroke="{OUTLINE}" stroke-width="2" stroke-linejoin="round">{flicker_a}</polygon>'
        f'</g>'
    )
    rocket_children.append(flame_group)

    # ascent: gentle curved trajectory, slow off the pad then accelerating up
    # and out of frame - calcMode=spline + keyPoints drives the ease-in feel
    ascent_dx, ascent_dy = 40, -(h - ground_y + 250)  # clears the canvas with room to spare
    path_d = f"M0,0 C 30,{ascent_dy*0.35:.0f} {-ascent_dx},{ascent_dy*0.7:.0f} {ascent_dx},{ascent_dy}"
    t0, t1, t2 = 0.0, round(t_ignite / cycle, 4), round(t_launch_end / cycle, 4)
    motion_anim = (
        f'<animateMotion path="{path_d}" keyPoints="0;0;1;1" keyTimes="{t0};{t1};{t2};1" '
        f'calcMode="spline" keySplines="0 0 1 1;0.42 0 1 1;0 0 1 1" '
        f'dur="{cycle:.3f}s" repeatCount="indefinite"/>'
    )
    # slight clockwise tilt as it climbs, on top of the arc translation
    tilt_anim = _stepped_anim(
        "transform", cycle,
        [(0.0, f"rotate(0 {pad_x:.0f} {ground_y})"), (t_ignite, f"rotate(0 {pad_x:.0f} {ground_y})"),
         (t_launch_end, f"rotate(14 {pad_x:.0f} {ground_y})")],
        tag="animateTransform", extra=f'type="rotate" additive="sum"',
    )
    parts.append(f'<g>{motion_anim}{tilt_anim}{"".join(rocket_children)}</g>')

    # ground dust/smoke puffs at liftoff (ground-anchored, not attached to the rocket)
    for i in range(4):
        smoke_dx = (-1) ** i * (16 + i * 16)
        smoke_appear = t_ignite + i * 0.15
        smoke_anim = _stepped_anim(
            "opacity", cycle,
            [(0.0, "0"), (smoke_appear, "0"), (smoke_appear + 0.05, "0.85"), (smoke_appear + 1.1, "0")],
        )
        parts.append(
            f'<g opacity="0">{smoke_anim}'
            + _outlined_rect(pad_x + smoke_dx - 10, ground_y - 4, 20, 20, SMOKE_COLOR, sw=1.5)
            + '</g>'
        )

    # "IT'S DONE" end card, once the rocket has fully cleared the frame
    end_anim = _stepped_anim(
        "opacity", cycle,
        [(0.0, "0"), (t_endcard_start, "0"), (t_endcard_start + 0.2, "1"), (t_endcard_end, "1"), (t_endcard_end + 0.3, "0")],
    )
    parts.append(
        f'<text x="{pad_x:.0f}" y="{ground_y-160}" text-anchor="middle" font-family="Consolas, Menlo, monospace" '
        f'font-weight="700" font-size="52" letter-spacing="6" fill="{ROCKET_WHITE}" stroke="{OUTLINE}" '
        f'stroke-width="7" paint-order="stroke" stroke-linejoin="round" opacity="0">IT\'S DONE{end_anim}</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    commits_today = get_todays_contributions()
    sizes = layer_sizes(commits_today)
    nn_svg = build_svg(sizes)

    last_30 = get_last_30_days_contributions()
    chart_svg = build_contribution_chart(last_30)

    repos = _fetch_user_repos()
    core_svg = build_core_telemetry(repos)

    streak = get_current_streak()
    rocket_svg = build_rocket(streak)

    os.makedirs("dist", exist_ok=True)
    outputs = {
        "dist/neural-network.svg": nn_svg,
        "dist/contribution-telemetry.svg": chart_svg,
        "dist/core-telemetry.svg": core_svg,
        "dist/rocket.svg": rocket_svg,
    }
    for path, svg in outputs.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
    print(f"today's contributions: {commits_today} -> layer sizes {sizes}")
    print(f"30-day chart points: {len(last_30)}, repos: {len(repos)}")
    print(f"current streak: {streak} -> rocket pieces {pieces_for_streak(streak)}/{ROCKET_PIECE_CAP}")


if __name__ == "__main__":
    main()
