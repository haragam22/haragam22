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


def get_todays_contributions():
    if not TOKEN or not USERNAME:
        print("warning: GH_PAT/GH_USERNAME not set, defaulting to 0 contributions")
        return 0
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
        print(f"warning: contribution lookup failed ({exc}), defaulting to 0")
        return 0
    today = datetime.date.today().isoformat()
    for week in weeks:
        for day in week["contributionDays"]:
            if day["date"] == today:
                return day["contributionCount"]
    return 0


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


def main():
    commits = get_todays_contributions()
    sizes = layer_sizes(commits)
    svg = build_svg(sizes)
    os.makedirs("dist", exist_ok=True)
    with open("dist/neural-network.svg", "w") as f:
        f.write(svg)
    print(f"today's contributions: {commits} -> layer sizes {sizes}")


if __name__ == "__main__":
    main()
