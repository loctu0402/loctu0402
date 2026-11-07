import os
import statistics
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

import requests

LOGIN = os.environ.get("PROFILE_LOGIN", "loctu0402")
OUT = Path(__file__).resolve().parents[1] / "assets" / "activity-report.svg"
ICT = timezone(timedelta(hours=7))
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) { totalCount }
  }
}
"""


def fetch_days(token, today):
    days, repos = {}, 0
    for back in (1, 0):
        start = today - timedelta(days=365 * (back + 1))
        end = today - timedelta(days=365 * back)
        r = requests.post("https://api.github.com/graphql", timeout=30, headers={"Authorization": f"bearer {token}"},
                          json={"query": QUERY, "variables": {"login": LOGIN, "from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"}})
        r.raise_for_status()
        user = r.json()["data"]["user"]
        repos = user["repositories"]["totalCount"]
        for w in user["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[date.fromisoformat(d["date"])] = d["contributionCount"]
    return days, repos


def months_back(today, n):
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def month_days(y, m):
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return (nxt - date(y, m, 1)).days


def build(days, today):
    totals = {}
    for d, c in days.items():
        totals[(d.year, d.month)] = totals.get((d.year, d.month), 0) + c
    months = months_back(today, 18)
    rows = []
    for i, (y, m) in enumerate(months[6:], start=6):
        prior = [totals.get(k, 0) for k in months[i - 6:i]]
        med = statistics.median(prior)
        mad = statistics.median(abs(p - med) for p in prior)
        scale = today.day / month_days(y, m) if (y, m) == (today.year, today.month) else 1.0
        expected, band = med * scale, max(3 * 1.4826 * mad * scale, 0.1 * med * scale, 1)
        actual = totals.get((y, m), 0)
        verdict = "above" if actual > expected + band else "below" if actual < expected - band else "normal"
        rows.append({"label": date(y, m, 1).strftime("%b"), "actual": actual, "expected": expected, "band": band, "verdict": verdict})
    window = [today - timedelta(days=i) for i in range(365)]
    active = sum(days.get(d, 0) > 0 for d in window)
    streak = best = 0
    for d in sorted(window):
        streak = streak + 1 if days.get(d, 0) > 0 else 0
        best = max(best, streak)
    return rows, sum(days.get(d, 0) for d in window), active, best


def render(rows, total, active, best, repos, today):
    w, h, x0, y0, bw, gap, ch = 900, 350, 470, 78, 26, 8, 190
    top = max(max(r["actual"], r["expected"] + r["band"]) for r in rows) or 1
    colour = {"above": "#34d399", "normal": "#94a3b8", "below": "#f87171"}
    cur = rows[-1]
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="Inter, Segoe UI, Arial, sans-serif">',
         f'<rect width="{w}" height="{h}" rx="18" fill="#0b1220"/>',
         f'<text x="32" y="42" fill="#94a3b8" font-size="12" font-weight="700" letter-spacing=".08em">DAILY REPORT · MY GITHUB ACTIVITY · {today:%d %b %Y}</text>',
         f'<text x="32" y="108" fill="#f8fafc" font-size="56" font-weight="800">{total:,}</text>',
         '<text x="32" y="134" fill="#94a3b8" font-size="14">contributions in the last 12 months</text>']
    chips = [
        (f"This month {cur['actual']} vs {cur['expected']:.0f} expected", colour[cur["verdict"]], cur["verdict"]),
        (f"Active on {active} of 365 days", "#38bdf8", ""),
        (f"Longest streak {best} days", "#facc15", ""),
        (f"{repos} public repositories", "#c084fc", ""),
    ]
    for i, (text, c, tag) in enumerate(chips):
        y = 158 + i * 34
        p.append(f'<rect x="32" y="{y}" width="370" height="26" rx="13" fill="#111a2e" stroke="{c}" stroke-opacity=".6"/>')
        p.append(f'<circle cx="48" cy="{y + 13}" r="4" fill="{c}"/>')
        p.append(f'<text x="62" y="{y + 17.5}" fill="#e2e8f0" font-size="12.5">{escape(text)}{" · " + tag if tag else ""}</text>')
    for i, r in enumerate(rows):
        x = x0 + i * (bw + gap)
        lo, hi = max(r["expected"] - r["band"], 0), r["expected"] + r["band"]
        yb = y0 + ch - hi / top * ch
        p.append(f'<rect x="{x - 3}" y="{yb:.1f}" width="{bw + 6}" height="{(hi - lo) / top * ch:.1f}" rx="4" fill="#334155" fill-opacity=".22"/>')
        bh = r["actual"] / top * ch
        p.append(f'<rect x="{x}" y="{y0 + ch - bh:.1f}" width="{bw}" height="{bh:.1f}" rx="5" fill="{colour[r["verdict"]]}" fill-opacity="{1 if i == len(rows) - 1 else .75}"/>')
        ye = y0 + ch - r["expected"] / top * ch
        p.append(f'<line x1="{x - 3}" x2="{x + bw + 3}" y1="{ye:.1f}" y2="{ye:.1f}" stroke="#e2e8f0" stroke-width="1.5" stroke-dasharray="3 3"/>')
        p.append(f'<text x="{x + bw / 2}" y="{y0 + ch + 18}" fill="#94a3b8" font-size="11" text-anchor="middle">{r["label"]}</text>')
    p.append(f'<text x="{x0}" y="{y0 - 22}" fill="#e2e8f0" font-size="13" font-weight="700">Monthly contributions against expected</text>')
    p.append(f'<text x="{x0}" y="{y0 - 6}" fill="#94a3b8" font-size="11">Dashed line: median of the six months before. Grey band: three MADs.</text>')
    p.append(f'<text x="32" y="{h - 18}" fill="#64748b" font-size="11">Redrawn every morning by a GitHub Action from the GraphQL API, the same way I check business metrics against an expected value.</text>')
    p.append("</svg>")
    return "\n".join(p)


def main():
    today = datetime.now(ICT).date()
    days, repos = fetch_days(os.environ["GITHUB_TOKEN"], today)
    rows, total, active, best = build(days, today)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(rows, total, active, best, repos, today), encoding="utf-8")
    print(f"{OUT.name}: {total} contributions, this month {rows[-1]['actual']} ({rows[-1]['verdict']})")


if __name__ == "__main__":
    main()
