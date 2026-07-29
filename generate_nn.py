"""
Generates an animated SVG: a CNN-style tapering network whose layer sizes
reflect today's GitHub contribution count, with a pac-man sprite that eats
(dims) nodes layer by layer, left to right, then glows back to full
brightness and loops.

Env vars required:
  GH_USERNAME - your GitHub username
  GH_PAT      - a classic personal access token with `read:user` scope
                (the default GITHUB_TOKEN in Actions cannot read your
                contribution calendar via the `viewer`/`user` GraphQL field)
"""
import os
import datetime
import requests

USERNAME = os.environ["GH_USERNAME"]
TOKEN = os.environ["GH_PAT"]

WIDTH, HEIGHT = 680, 300
BG = "#0d1117"
NODE_ON = "#58a6ff"
NODE_OFF = "#30363d"
EDGE = "#1f6feb"
PACMAN_YELLOW = "#f4d03f"

CYCLE = 10.0          # total seconds per full loop
TRAVEL_FRACTION = 0.75  # fraction of CYCLE spent eating (rest = glow-back-up)


def get_todays_contributions():
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
    resp = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": {"login": USERNAME}},
        headers={"Authorization": f"bearer {TOKEN}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    today = datetime.date.today().isoformat()
    for week in weeks:
        for day in week["contributionDays"]:
            if day["date"] == today:
                return day["contributionCount"]
    return 0


def layer_sizes(commits):
    # CNN-ish taper: wide input, narrowing toward output.
    base = [6, 5, 4, 3, 2]
    boost = min(commits, 12) // 2  # every 2 commits today adds a node per layer
    return [min(n + boost, 9) for n in base]


def build_svg(sizes):
    n_layers = len(sizes)
    margin_x = 70
    usable_w = WIDTH - 2 * margin_x
    xs = [margin_x + usable_w * i / (n_layers - 1) for i in range(n_layers)]

    nodes = []  # (x, y, layer_index)
    for li, count in enumerate(sizes):
        gap = (HEIGHT - 60) / (count + 1)
        for i in range(count):
            y = 40 + gap * (i + 1)
            nodes.append({"x": xs[li], "y": y, "layer": li})

    travel_end = CYCLE * TRAVEL_FRACTION

    def arrive_time(li):
        return travel_end * li / (n_layers - 1)

    svg_parts = [
        f'<svg width="100%" viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{BG}"/>',
    ]

    # edges between adjacent layers (funnel, every node to every node keeps it too busy for
    # dense layers, so connect each node to the 2 nearest nodes in the next layer)
    svg_parts.append(f'<g stroke="{EDGE}" stroke-width="0.5" opacity="0.25">')
    for li in range(n_layers - 1):
        layer_a = [n for n in nodes if n["layer"] == li]
        layer_b = [n for n in nodes if n["layer"] == li + 1]
        for a in layer_a:
            layer_b_sorted = sorted(layer_b, key=lambda b: abs(b["y"] - a["y"]))
            for b in layer_b_sorted[:2]:
                svg_parts.append(f'<line x1="{a["x"]:.1f}" y1="{a["y"]:.1f}" x2="{b["x"]:.1f}" y2="{b["y"]:.1f}"/>')
    svg_parts.append("</g>")

    # nodes, each with its own dim/reset animation timed to pac-man's arrival
    for n in nodes:
        t_arrive = arrive_time(n["layer"])
        t_dim_end = min(t_arrive + 0.4, travel_end)
        key_times = [0, t_arrive / CYCLE, t_dim_end / CYCLE, 0.9, 1]
        # guard against non-increasing keyTimes when a layer arrives at t=0
        key_times = sorted(set(round(k, 4) for k in key_times))
        if len(key_times) < 4:
            key_times = [0, 0.01, 0.9, 1]
        kt_str = ";".join(str(k) for k in key_times)
        values = ";".join(["1", "0.15", "0.15", "1"][: len(key_times)])
        svg_parts.append(
            f'<circle cx="{n["x"]:.1f}" cy="{n["y"]:.1f}" r="8" fill="{NODE_ON}">'
            f'<animate attributeName="fill" values="{NODE_ON};{NODE_OFF};{NODE_OFF};{NODE_ON}" '
            f'keyTimes="{kt_str}" dur="{CYCLE}s" repeatCount="indefinite"/>'
            f"</circle>"
        )

    # pac-man: yellow circle + chomping wedge, moving left to right along mid-height,
    # fading out during the reset phase and reappearing at the start of each cycle
    mid_y = HEIGHT / 2
    path_pts = " L ".join(f'{x:.1f},{mid_y:.1f}' for x in xs)
    key_times_p = ";".join(str(round(arrive_time(li) / CYCLE, 4)) for li in range(n_layers))
    svg_parts.append(
        f'<g fill="{PACMAN_YELLOW}">'
        f'<animate attributeName="opacity" values="1;1;0;0;1" keyTimes="0;{TRAVEL_FRACTION};{TRAVEL_FRACTION + 0.02};0.98;1" '
        f'dur="{CYCLE}s" repeatCount="indefinite"/>'
        f'<circle r="12">'
        f'<animateMotion path="M {path_pts}" keyTimes="{key_times_p}" '
        f'keyPoints="{";".join(str(round(i/(n_layers-1),4)) for i in range(n_layers))}" '
        f'calcMode="linear" dur="{CYCLE}s" repeatCount="indefinite"/>'
        f'</circle>'
        f'<path d="M 0,0 L 12,-6 A 12 12 0 1 1 12,6 Z" fill="{BG}">'
        f'<animateMotion path="M {path_pts}" keyTimes="{key_times_p}" '
        f'keyPoints="{";".join(str(round(i/(n_layers-1),4)) for i in range(n_layers))}" '
        f'calcMode="linear" dur="{CYCLE}s" repeatCount="indefinite"/>'
        f'<animateTransform attributeName="transform" type="rotate" '
        f'values="0;25;0;-25;0" dur="0.5s" repeatCount="indefinite" additive="sum"/>'
        f'</path>'
        f'</g>'
    )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


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