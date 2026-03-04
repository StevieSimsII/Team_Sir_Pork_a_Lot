"""
dashboard/generate.py

Fetches the current-year raffle data from SharePoint via Microsoft Graph API
and renders a self-contained neon-themed HTML dashboard to dashboard/dist/index.html
"""

import json
import os
import sys
from datetime import datetime, timezone
from collections import defaultdict

import requests

# ── Config from environment ───────────────────────────────────────────────────

TENANT_ID   = os.environ["AZURE_TENANT_ID"]
CLIENT_ID   = os.environ["AZURE_CLIENT_ID"]
CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]
SP_HOSTNAME = os.environ.get("SHAREPOINT_HOSTNAME", "kingsofcode.sharepoint.com")
SP_SITE_PATH = os.environ.get("SHAREPOINT_SITE_PATH", "/sites/StevieCopilot")
LIST_ID     = os.environ["SHAREPOINT_LIST_ID"]
GOAL        = int(os.environ.get("GOAL_AMOUNT", "30000"))
CURRENT_YEAR = datetime.now(timezone.utc).year

# ── Auth ──────────────────────────────────────────────────────────────────────

def get_token() -> str:
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    resp = requests.post(url, data={
        "grant_type":    "client_credentials",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope":         "https://graph.microsoft.com/.default",
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]

def graph(token: str, url: str) -> dict:
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json()

# ── Data fetch ────────────────────────────────────────────────────────────────

def get_site_id(token: str) -> str:
    data = graph(token, f"https://graph.microsoft.com/v1.0/sites/{SP_HOSTNAME}:{SP_SITE_PATH}")
    return data["id"]

def get_list_items(token: str, site_id: str) -> list[dict]:
    """Fetch all current-year items with pagination."""
    year_start = f"{CURRENT_YEAR}-01-01T00:00:00Z"
    year_end   = f"{CURRENT_YEAR + 1}-01-01T00:00:00Z"
    filter_q   = f"fields/SubmissionDate ge '{year_start}' and fields/SubmissionDate lt '{year_end}'"
    url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{LIST_ID}/items"
        f"?$expand=fields"
        f"&$filter={requests.utils.quote(filter_q)}"
        f"&$top=999"
    )
    items = []
    while url:
        data = graph(token, url)
        items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return items

# ── Processing ────────────────────────────────────────────────────────────────

def process(items: list[dict]) -> dict:
    total_raised   = 0
    total_tickets  = 0
    buyers         = set()
    daily_totals   = defaultdict(float)   # "YYYY-MM-DD" → $
    tier_counts    = defaultdict(int)     # ticket count → # of orders
    top_buyers     = defaultdict(float)   # person → total $

    for item in items:
        f = item.get("fields", {})
        amount  = float(f.get("TotalPaid", 0) or 0)
        tickets = int(f.get("NumberofChances", 0) or 0)
        person  = str(f.get("Person", "Unknown") or "Unknown").strip()
        date_str = f.get("SubmissionDate", "")

        total_raised  += amount
        total_tickets += tickets
        buyers.add(person.lower())
        top_buyers[person] += amount

        if tickets > 0:
            tier_counts[tickets] += 1

        if date_str:
            try:
                day = date_str[:10]   # "YYYY-MM-DD"
                daily_totals[day] += amount
            except Exception:
                pass

    # Sort daily totals
    sorted_days = sorted(daily_totals.keys())
    # Top 5 buyers
    top5 = sorted(top_buyers.items(), key=lambda x: x[1], reverse=True)[:5]
    # Tier labels
    tier_labels = {1: "1 Ticket ($25)", 3: "3 Tickets ($60)", 6: "6 Tickets ($100)", 12: "12 Tickets ($200)"}
    tiers = [(tier_labels.get(k, f"{k} Tickets"), v) for k, v in sorted(tier_counts.items())]

    return {
        "total_raised":  total_raised,
        "total_tickets": total_tickets,
        "buyer_count":   len(buyers),
        "avg_order":     total_raised / len(buyers) if buyers else 0,
        "daily_labels":  sorted_days,
        "daily_values":  [daily_totals[d] for d in sorted_days],
        "tier_labels":   [t[0] for t in tiers],
        "tier_values":   [t[1] for t in tiers],
        "top5":          top5,
        "goal":          GOAL,
        "pct":           min(100, round(total_raised / GOAL * 100, 1)),
        "year":          CURRENT_YEAR,
        "updated_at":    datetime.now(timezone.utc).strftime("%B %d, %Y %I:%M %p UTC"),
    }

# ── HTML generation ───────────────────────────────────────────────────────────

def render_html(d: dict) -> str:
    top5_rows = "".join(
        f'<tr><td class="td-name">{name}</td><td class="td-amount">${amt:,.0f}</td></tr>'
        for name, amt in d["top5"]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Sir Pork-a-Lot · Raffle Dashboard {d['year']}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg:      #0f0820;
      --card:    #1a0f35;
      --cyan:    #00e5ff;
      --pink:    #ff00cc;
      --gold:    #ffd700;
      --purple:  #c084fc;
      --text:    #f0e6ff;
      --muted:   #a78bca;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: radial-gradient(ellipse at 50% 0%, rgba(160,80,255,.22) 0%, transparent 55%),
                  linear-gradient(180deg, #0f0820 0%, #1a0d35 100%);
      min-height: 100vh;
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      padding: 2rem 1rem 4rem;
    }}
    /* ── Header ── */
    .header {{
      text-align: center;
      margin-bottom: 2.5rem;
    }}
    .header img {{
      width: 140px;
      mix-blend-mode: screen;
      filter: drop-shadow(0 0 28px rgba(255,0,204,.65));
      margin-bottom: .75rem;
    }}
    .header h1 {{
      font-size: 1.5rem;
      font-weight: 800;
      letter-spacing: .12em;
      text-transform: uppercase;
      color: var(--purple);
    }}
    .header .sub {{
      font-size: .9rem;
      color: var(--muted);
      margin-top: .25rem;
    }}
    .divider {{
      height: 1px;
      background: linear-gradient(90deg, transparent, var(--pink), var(--cyan), var(--pink), transparent);
      box-shadow: 0 0 8px rgba(255,0,204,.5);
      max-width: 360px;
      margin: .75rem auto 0;
    }}
    /* ── Grid ── */
    .grid {{
      max-width: 960px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1.25rem;
      margin-bottom: 1.5rem;
    }}
    .card {{
      background: rgba(26,15,53,.75);
      border: 1px solid rgba(192,132,252,.25);
      border-radius: 1rem;
      padding: 1.4rem 1.5rem;
    }}
    .card-label {{
      font-size: .75rem;
      text-transform: uppercase;
      letter-spacing: .08em;
      color: var(--muted);
      margin-bottom: .4rem;
    }}
    .card-value {{
      font-size: 2rem;
      font-weight: 800;
      line-height: 1.1;
    }}
    .cyan  {{ color: var(--cyan);   text-shadow: 0 0 12px rgba(0,229,255,.6); }}
    .gold  {{ color: var(--gold);   text-shadow: 0 0 12px rgba(255,215,0,.6); }}
    .pink  {{ color: var(--pink);   text-shadow: 0 0 12px rgba(255,0,204,.6); }}
    .purp  {{ color: var(--purple); text-shadow: 0 0 12px rgba(192,132,252,.6); }}
    /* ── Goal bar ── */
    .goal-card {{
      max-width: 960px;
      margin: 0 auto 1.5rem;
      background: rgba(26,15,53,.75);
      border: 1px solid rgba(255,215,0,.3);
      border-radius: 1rem;
      padding: 1.4rem 1.75rem;
    }}
    .goal-header {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: .75rem;
    }}
    .goal-title {{
      font-size: 1rem;
      font-weight: 700;
      color: var(--gold);
      text-shadow: 0 0 10px rgba(255,215,0,.6);
    }}
    .goal-pct {{
      font-size: 1.4rem;
      font-weight: 800;
      color: var(--gold);
    }}
    .bar-track {{
      background: rgba(255,255,255,.07);
      border-radius: 9999px;
      height: 18px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 9999px;
      background: linear-gradient(90deg, #cc00aa, #ff00cc, #ffd700);
      box-shadow: 0 0 16px rgba(255,0,204,.5);
      transition: width .6s ease;
      width: {d['pct']}%;
    }}
    .goal-sub {{
      display: flex;
      justify-content: space-between;
      font-size: .8rem;
      color: var(--muted);
      margin-top: .5rem;
    }}
    /* ── Charts row ── */
    .charts-row {{
      max-width: 960px;
      margin: 0 auto 1.5rem;
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 1.25rem;
    }}
    @media (max-width: 640px) {{
      .charts-row {{ grid-template-columns: 1fr; }}
    }}
    .chart-card {{
      background: rgba(26,15,53,.75);
      border: 1px solid rgba(192,132,252,.25);
      border-radius: 1rem;
      padding: 1.25rem;
    }}
    .chart-title {{
      font-size: .8rem;
      text-transform: uppercase;
      letter-spacing: .08em;
      color: var(--muted);
      margin-bottom: 1rem;
    }}
    /* ── Top buyers ── */
    .leaderboard {{
      max-width: 960px;
      margin: 0 auto 1.5rem;
      background: rgba(26,15,53,.75);
      border: 1px solid rgba(192,132,252,.25);
      border-radius: 1rem;
      padding: 1.4rem 1.75rem;
    }}
    .lb-title {{
      font-size: .8rem;
      text-transform: uppercase;
      letter-spacing: .08em;
      color: var(--muted);
      margin-bottom: 1rem;
    }}
    table {{ width: 100%; border-collapse: collapse; }}
    tr:not(:last-child) td {{ border-bottom: 1px solid rgba(192,132,252,.12); }}
    td {{ padding: .6rem .25rem; font-size: .95rem; }}
    .td-name   {{ color: var(--text); }}
    .td-amount {{ text-align: right; font-weight: 700; color: var(--cyan);
                  text-shadow: 0 0 8px rgba(0,229,255,.4); }}
    /* ── Footer ── */
    .footer {{
      text-align: center;
      margin-top: 2rem;
      font-size: .75rem;
      color: rgba(167,139,202,.4);
    }}
  </style>
</head>
<body>

  <div class="header">
    <img src="https://sirporkalot.vercel.app/Photo_2.jpeg" alt="Sir Pork-a-Lot" />
    <h1>Raffle Dashboard {d['year']}</h1>
    <p class="sub">Hogs for the Cause · Last updated {d['updated_at']}</p>
    <div class="divider"></div>
  </div>

  <!-- Stat cards -->
  <div class="grid">
    <div class="card">
      <div class="card-label">💰 Total Raised</div>
      <div class="card-value gold">${d['total_raised']:,.0f}</div>
    </div>
    <div class="card">
      <div class="card-label">🎟️ Tickets Sold</div>
      <div class="card-value cyan">{d['total_tickets']}</div>
    </div>
    <div class="card">
      <div class="card-label">👥 Total Buyers</div>
      <div class="card-value purp">{d['buyer_count']}</div>
    </div>
    <div class="card">
      <div class="card-label">📊 Avg Order</div>
      <div class="card-value pink">${d['avg_order']:,.0f}</div>
    </div>
  </div>

  <!-- Goal progress -->
  <div class="goal-card">
    <div class="goal-header">
      <span class="goal-title">🎯 Goal Progress — ${d['goal']:,}</span>
      <span class="goal-pct">{d['pct']}%</span>
    </div>
    <div class="bar-track"><div class="bar-fill"></div></div>
    <div class="goal-sub">
      <span>${d['total_raised']:,.0f} raised</span>
      <span>${d['goal'] - d['total_raised']:,.0f} to go</span>
    </div>
  </div>

  <!-- Charts -->
  <div class="charts-row">
    <div class="chart-card">
      <div class="chart-title">📅 Daily Sales ($)</div>
      <canvas id="barChart"></canvas>
    </div>
    <div class="chart-card">
      <div class="chart-title">🎟️ Ticket Tier Mix</div>
      <canvas id="donutChart"></canvas>
    </div>
  </div>

  <!-- Top buyers -->
  <div class="leaderboard">
    <div class="lb-title">🏆 Top Supporters</div>
    <table>
      <tbody>
        {top5_rows if top5_rows else '<tr><td class="td-name" colspan="2" style="color:var(--muted);text-align:center">No data yet</td></tr>'}
      </tbody>
    </table>
  </div>

  <div class="footer">&copy; {d['year']} Team Sir Pork a Lot &mdash; Hogs for the Cause</div>

  <script>
    const CYAN   = "#00e5ff";
    const PINK   = "#ff00cc";
    const GOLD   = "#ffd700";
    const PURPLE = "#c084fc";

    // Bar chart — daily sales
    new Chart(document.getElementById("barChart"), {{
      type: "bar",
      data: {{
        labels: {json.dumps(d['daily_labels'])},
        datasets: [{{
          label: "Daily Sales ($)",
          data: {json.dumps(d['daily_values'])},
          backgroundColor: "rgba(0,229,255,.25)",
          borderColor: CYAN,
          borderWidth: 2,
          borderRadius: 6,
        }}]
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          x: {{ ticks: {{ color: "#a78bca", maxRotation: 45 }}, grid: {{ color: "rgba(192,132,252,.1)" }} }},
          y: {{ ticks: {{ color: "#a78bca", callback: v => "$" + v }}, grid: {{ color: "rgba(192,132,252,.1)" }} }}
        }}
      }}
    }});

    // Donut chart — tier mix
    new Chart(document.getElementById("donutChart"), {{
      type: "doughnut",
      data: {{
        labels: {json.dumps(d['tier_labels'])},
        datasets: [{{
          data: {json.dumps(d['tier_values'])},
          backgroundColor: [CYAN, PINK, GOLD, PURPLE],
          borderColor: "#0f0820",
          borderWidth: 3,
          hoverOffset: 8,
        }}]
      }},
      options: {{
        responsive: true,
        plugins: {{
          legend: {{ position: "bottom", labels: {{ color: "#a78bca", padding: 14, font: {{ size: 11 }} }} }},
        }}
      }}
    }});
  </script>
</body>
</html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Authenticating to Microsoft Graph...")
    token = get_token()

    print("Resolving SharePoint site ID...")
    site_id = get_site_id(token)
    print(f"  Site ID: {site_id}")

    print(f"Fetching {CURRENT_YEAR} list items...")
    items = get_list_items(token, site_id)
    print(f"  Found {len(items)} items")

    print("Processing data...")
    data = process(items)
    print(f"  Total raised: ${data['total_raised']:,.0f} / ${data['goal']:,} ({data['pct']}%)")

    print("Rendering HTML...")
    html = render_html(data)

    out_dir = os.path.join(os.path.dirname(__file__), "dist")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved to {out_path}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
