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
# Isometric pixel-art rocket: assembles from streak length, fuels, rolls out,
# launches, resets, loops. Native SMIL only (no <script>, same GitHub-README
# constraint as everything else in this file).
# ---------------------------------------------------------------------------

# streak -> pieces assembled mapping: one piece per streak day, capped at 6
# (nose, upper body, lower body, fins, engine, plus a top antenna/greeble).
# streak 0 or 1 day -> bare gantry, no pieces. streak >= 6 -> fully built.
# tune ROCKET_PIECE_CAP to change how many days it takes to "complete" the rocket.
ROCKET_PIECE_CAP = 6

ROCKET_BG = "#0d1117"
ROCKET_STRUCT = "#30363d"
ROCKET_STRUCT_LIGHT = "#8b949e"
ROCKET_BODY = "#c9d1d9"
ROCKET_ACCENT = "#58a6ff"
ROCKET_FLAME_A = "#ffd23f"
ROCKET_FLAME_B = "#ff6b35"
ROCKET_SMOKE = "#484f58"


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


def build_rocket(streak):
    n_pieces = pieces_for_streak(streak)

    w, h = 420, 320
    cycle = 14.0
    t_assembly_end = cycle * 0.40
    t_fuel_end = cycle * 0.55
    t_rollout_end = cycle * 0.70
    t_launch_end = cycle * 0.90
    # reset phase fills the remainder of the cycle back to 1.0

    gantry_x, ground_y = 110, 260
    pad_x = 300  # where the crawler delivers the rocket for launch
    rollout_dx = pad_x - gantry_x

    parts = [
        f'<svg width="100%" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
        f'shape-rendering="crispEdges">',
        f'<rect width="{w}" height="{h}" fill="{ROCKET_BG}"/>',
        f'<rect x="0" y="{ground_y+18}" width="{w}" height="{h-ground_y-18}" fill="#161b22"/>',
    ]

    # static gantry truss (assembly pad, left side)
    parts.append(f'<g stroke="{ROCKET_STRUCT_LIGHT}" stroke-width="3" fill="none">')
    parts.append(f'<line x1="{gantry_x-34}" y1="{ground_y+18}" x2="{gantry_x-34}" y2="{ground_y-160}"/>')
    parts.append(f'<line x1="{gantry_x+34}" y1="{ground_y+18}" x2="{gantry_x+34}" y2="{ground_y-160}"/>')
    for gy in range(ground_y - 150, ground_y + 10, 30):
        parts.append(f'<line x1="{gantry_x-34}" y1="{gy}" x2="{gantry_x+34}" y2="{gy}"/>')
    parts.append("</g>")

    # launch pad marker (right side, blocky iso platform)
    parts.append(
        f'<polygon points="{pad_x-40},{ground_y+18} {pad_x+40},{ground_y+18} {pad_x+30},{ground_y+38} {pad_x-30},{ground_y+38}" '
        f'fill="{ROCKET_STRUCT}"/>'
    )

    # rocket pieces, stacked bottom-up: engine, lower body, fins, upper body, nose, antenna
    piece_h = 30
    piece_defs = [
        ("engine", ground_y, 20, ROCKET_STRUCT),
        ("lower body", ground_y - piece_h, 18, ROCKET_BODY),
        ("fins", ground_y - piece_h * 2, 26, ROCKET_ACCENT),
        ("upper body", ground_y - piece_h * 2 - 20, 18, ROCKET_BODY),
        ("nose", ground_y - piece_h * 3 - 20, 22, ROCKET_ACCENT),
        ("antenna", ground_y - piece_h * 3 - 42, 8, ROCKET_STRUCT_LIGHT),
    ]

    rocket_children = []
    for i, (name, y, half_w, color) in enumerate(piece_defs):
        visible = i < n_pieces
        appear_t = (i + 1) * (t_assembly_end / (ROCKET_PIECE_CAP + 1))
        cy = y - 12
        if not visible:
            continue
        drop_from = cy - 60
        # piece drops into place then flashes white briefly on landing ("thunk")
        translate_anim = _stepped_anim(
            "transform", cycle,
            [(0.0, f"translate(0,{drop_from-cy})"), (appear_t, f"translate(0,{drop_from-cy})"),
             (appear_t + 0.35, "translate(0,0)")],
            tag="animateTransform", extra='type="translate" additive="sum"',
        )
        opacity_anim = _stepped_anim(
            "opacity", cycle,
            [(0.0, "0"), (appear_t, "0"), (appear_t + 0.01, "1")],
        )
        flash_anim = _stepped_anim(
            "opacity", cycle,
            [(0.0, "0"), (appear_t + 0.35, "0"), (appear_t + 0.36, "0.9"), (appear_t + 0.55, "0")],
        )
        rocket_children.append(
            f'<g opacity="0">{opacity_anim}'
            f'<rect x="{gantry_x-half_w}" y="{cy-10}" width="{half_w*2}" height="20" fill="{color}">{translate_anim}</rect>'
            f'<rect x="{gantry_x-half_w}" y="{cy-10}" width="{half_w*2}" height="20" fill="#ffffff">{flash_anim}</rect>'
            f'</g>'
        )

    # whole assembled rocket translates: rollout (x) then launch (y, exits top of frame)
    rocket_transform = _stepped_anim(
        "transform", cycle,
        [
            (0.0, "translate(0,0)"),
            (t_assembly_end, "translate(0,0)"),
            (t_rollout_end, f"translate({rollout_dx},0)"),
            (t_launch_end, f"translate({rollout_dx},0)"),
            (cycle * 0.985, f"translate({rollout_dx},-420)"),
        ],
        tag="animateTransform", extra='type="translate"',
    )
    parts.append(f'<g>{rocket_transform}{"".join(rocket_children)}</g>')

    # fuel gauge: small vertical bar next to the gantry, fills during fueling phase
    gauge_x, gauge_top, gauge_h, gauge_w = gantry_x + 55, ground_y - 140, 130, 12
    fill_anim = _stepped_anim(
        "height", cycle,
        [(0.0, "0"), (t_assembly_end, "0"), (t_fuel_end, str(gauge_h))],
    )
    fill_y_anim = _stepped_anim(
        "y", cycle,
        [(0.0, str(gauge_top + gauge_h)), (t_assembly_end, str(gauge_top + gauge_h)), (t_fuel_end, str(gauge_top))],
    )
    parts.append(f'<rect x="{gauge_x}" y="{gauge_top}" width="{gauge_w}" height="{gauge_h}" fill="{ROCKET_STRUCT}"/>')
    parts.append(f'<rect x="{gauge_x}" y="{gauge_top+gauge_h}" width="{gauge_w}" height="0" fill="{ROCKET_FLAME_A}">{fill_anim}{fill_y_anim}</rect>')

    # ignition flash + blocky smoke puffs at the launch pad, right as the rocket lifts off
    ignite_t = t_rollout_end + (t_launch_end - t_rollout_end) * 0.15
    flame_anim = _stepped_anim(
        "opacity", cycle,
        [(0.0, "0"), (ignite_t, "0"), (ignite_t + 0.05, "1"), (t_launch_end, "1"), (t_launch_end + 0.3, "0")],
    )
    parts.append(
        f'<polygon points="{pad_x-14},{ground_y+18} {pad_x+14},{ground_y+18} {pad_x},{ground_y+55}" '
        f'fill="{ROCKET_FLAME_B}" opacity="0">{flame_anim}</polygon>'
    )
    for i in range(4):
        smoke_dx = (-1) ** i * (10 + i * 14)
        smoke_appear = ignite_t + i * 0.12
        smoke_anim = _stepped_anim(
            "opacity", cycle,
            [(0.0, "0"), (smoke_appear, "0"), (smoke_appear + 0.05, "0.8"), (smoke_appear + 1.0, "0")],
        )
        parts.append(
            f'<rect x="{pad_x+smoke_dx-8}" y="{ground_y+10}" width="16" height="16" fill="{ROCKET_SMOKE}" opacity="0">{smoke_anim}</rect>'
        )

    # reset label, visible only during the blank-pad reset beat
    label_anim = _stepped_anim(
        "opacity", cycle,
        [(0.0, "0"), (t_launch_end + 0.4, "0"), (t_launch_end + 0.5, "1"), (cycle * 0.99, "1"), (cycle * 0.995, "0")],
    )
    parts.append(
        f'<text x="{w/2:.0f}" y="{ground_y-10}" text-anchor="middle" font-family="monospace" font-size="12" '
        f'letter-spacing="2" fill="{ROCKET_STRUCT_LIGHT}" opacity="0">REBUILDING...{label_anim}</text>'
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
