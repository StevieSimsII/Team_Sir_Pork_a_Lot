"""
dashboard/generate.py

Fetches raffle data (all years) from SharePoint via Microsoft Graph API
and renders a self-contained neon-themed HTML dashboard to dashboard/dist/index.html.

Includes:
  - Current-year stats, goal bar, daily sales chart, tier donut, top 5
  - Year-over-year comparison card (revenue/tickets/buyers through same date)
  - Cumulative sales line chart: full prior year vs current year to date
  - Returning buyers table  (bought last year AND this year)
  - Prospects table         (bought last year, NOT yet this year — solicit these)
  - New buyers table        (first-timers this year)
"""

import csv
import html as html_lib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

# ── Config from environment ───────────────────────────────────────────────────

TENANT_ID     = os.environ["AZURE_TENANT_ID"]
CLIENT_ID     = os.environ["AZURE_CLIENT_ID"]
CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]
SP_HOSTNAME   = os.environ.get("SHAREPOINT_HOSTNAME", "kingsofcode.sharepoint.com")
SP_SITE_PATH  = os.environ.get("SHAREPOINT_SITE_PATH", "/sites/StevieCopilot")
LIST_ID       = os.environ["SHAREPOINT_LIST_ID"]
GOAL          = int(os.environ.get("GOAL_AMOUNT", "30000"))

_TZ          = ZoneInfo("America/Chicago")
TODAY        = datetime.now(_TZ).date()
CURRENT_YEAR = TODAY.year
PREV_YEAR    = CURRENT_YEAR - 1
SAME_DAY_PREV = date(PREV_YEAR, TODAY.month, TODAY.day)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH    = os.path.normpath(
    os.path.join(_SCRIPT_DIR, "..", "Hogs for the Cause 2025 Raffle.csv")
)

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
    """Fetch ALL items (all years) with pagination."""
    url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{LIST_ID}/items"
        f"?$expand=fields&$top=999"
    )
    all_items = []
    while url:
        data = graph(token, url)
        all_items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    print(f"  Total items in list: {len(all_items)}")
    return all_items


# ── Normalisation helpers ─────────────────────────────────────────────────────

def norm_name(n: str) -> str:
    return " ".join(str(n or "").lower().split())

def norm_phone(p: str) -> str:
    digits = re.sub(r"\D", "", str(p or ""))
    return digits[-10:] if len(digits) >= 10 else digits

def norm_email(e: str) -> str:
    return str(e or "").lower().strip()

def esc(s: str) -> str:
    return html_lib.escape(str(s or ""))


# ── CSV loader (2025 supplemental data) ──────────────────────────────────────

def load_csv_prev() -> list[dict]:
    rows: list[dict] = []
    try:
        with open(CSV_PATH, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                name  = (row.get("Name")          or "").strip()
                email = (row.get("Email Address") or "").strip()
                phone = (row.get("Phone Number")  or "").strip()
                if name:
                    rows.append({"name": name, "email": email, "phone": phone})
    except FileNotFoundError:
        print(f"  WARNING: CSV not found at {CSV_PATH}", file=sys.stderr)
    print(f"  CSV {PREV_YEAR} rows: {len(rows)}")
    return rows


# ── Buyer record ──────────────────────────────────────────────────────────────

class Buyer:
    __slots__ = ("name", "email", "phone",
                 "tickets_prev", "amount_prev",
                 "tickets_cur",  "amount_cur")
    def __init__(self, name="", email="", phone=""):
        self.name         = name
        self.email        = email
        self.phone        = phone
        self.tickets_prev = 0
        self.amount_prev  = 0.0
        self.tickets_cur  = 0
        self.amount_cur   = 0.0

# ── Processing ────────────────────────────────────────────────────────────────

def process(all_items: list[dict], csv_rows: list[dict]) -> dict:

    # ── Bucket items by year ──────────────────────────────────────────────────
    cur_fields:  list[dict] = []
    prev_fields: list[dict] = []
    for item in all_items:
        f  = item.get("fields", {})
        yr = (f.get("SubmissionDate") or "")[:4]
        if yr == str(CURRENT_YEAR):
            cur_fields.append(f)
        elif yr == str(PREV_YEAR):
            prev_fields.append(f)
    print(f"  {PREV_YEAR}: {len(prev_fields)} items,  {CURRENT_YEAR}: {len(cur_fields)} items")

    # ── Helper ────────────────────────────────────────────────────────────────
    def _key(email, phone, name):
        e = norm_email(email)
        p = norm_phone(phone)
        n = norm_name(name)
        return e if e else (p if p else n)

    # ── Current-year aggregates ───────────────────────────────────────────────
    total_raised  = 0.0
    total_tickets = 0
    buyers_cur    = set()
    daily_totals  = defaultdict(float)
    tier_counts   = defaultdict(int)
    top_buyers    = defaultdict(float)
    map_cur: dict[str, Buyer] = {}
    daily_cur: dict[str, float] = defaultdict(float)

    for f in cur_fields:
        amount  = float(f.get("TotalPaid", 0) or 0)
        tickets = int(f.get("NumberofChances", 0) or 0)
        person  = str(f.get("Person", "Unknown") or "Unknown").strip()
        email   = str(f.get("Email", "") or "").strip()
        phone   = str(f.get("Phone", "") or "").strip()
        day     = (f.get("SubmissionDate") or "")[:10]

        total_raised  += amount
        total_tickets += tickets
        buyers_cur.add(person.lower())
        top_buyers[person] += amount
        if tickets > 0:
            tier_counts[tickets] += 1
        if day:
            daily_totals[day] += amount
            daily_cur[day]    += amount

        k = _key(email, phone, person)
        if k not in map_cur:
            map_cur[k] = Buyer(name=person, email=email, phone=phone)
        map_cur[k].tickets_cur += tickets
        map_cur[k].amount_cur  += amount

    sorted_days = sorted(daily_totals.keys())
    top5 = sorted(top_buyers.items(), key=lambda x: x[1], reverse=True)[:5]
    tier_label_map = {1: "1 Ticket ($25)", 3: "3 Tickets ($60)", 6: "6 Tickets ($100)", 12: "12 Tickets ($200)"}
    tiers = [(tier_label_map.get(k, f"{k} Tickets"), v) for k, v in sorted(tier_counts.items())]

    # ── Previous-year aggregates (with same-date cutoff for YoY) ─────────────
    map_prev: dict[str, Buyer] = {}
    daily_prev: dict[str, float] = defaultdict(float)
    todate_prev_amt  = 0.0
    todate_prev_tix  = 0
    todate_prev_keys: set[str] = set()
    total_prev_amt   = 0.0
    total_prev_tix   = 0

    for f in prev_fields:
        amount  = float(f.get("TotalPaid", 0) or 0)
        tickets = int(f.get("NumberofChances", 0) or 0)
        person  = str(f.get("Person", "Unknown") or "Unknown").strip()
        email   = str(f.get("Email", "") or "").strip()
        phone   = str(f.get("Phone", "") or "").strip()
        day     = (f.get("SubmissionDate") or "")[:10]

        total_prev_amt  += amount
        total_prev_tix  += tickets
        if day:
            daily_prev[day] += amount
            if day <= str(SAME_DAY_PREV):
                todate_prev_amt  += amount
                todate_prev_tix  += tickets

        k = _key(email, phone, person)
        if day and day <= str(SAME_DAY_PREV):
            todate_prev_keys.add(k)
        if k not in map_prev:
            map_prev[k] = Buyer(name=person, email=email, phone=phone)
        map_prev[k].tickets_prev += tickets
        map_prev[k].amount_prev  += amount

    # Supplement with CSV rows
    for row in csv_rows:
        e_n = norm_email(row["email"])
        p_n = norm_phone(row["phone"])
        n_n = norm_name(row["name"])
        matched = None
        if e_n and e_n in map_prev:
            matched = e_n
        elif p_n and p_n in map_prev:
            matched = p_n
        else:
            for k, b in map_prev.items():
                if norm_name(b.name) == n_n:
                    matched = k; break
        if matched:
            b = map_prev[matched]
            if not b.email and row["email"]: b.email = row["email"]
            if not b.phone and row["phone"]: b.phone = row["phone"]
        else:
            k = e_n or p_n or n_n
            if k and k not in map_prev:
                map_prev[k] = Buyer(name=row["name"], email=row["email"], phone=row["phone"])

    # ── Cross-reference: returning / prospects / new ──────────────────────────
    emails_cur = {norm_email(b.email)  for b in map_cur.values() if b.email}
    phones_cur = {norm_phone(b.phone)  for b in map_cur.values() if b.phone}
    names_cur  = {norm_name(b.name)    for b in map_cur.values()}
    emails_prev = {norm_email(b.email) for b in map_prev.values() if b.email}
    phones_prev = {norm_phone(b.phone) for b in map_prev.values() if b.phone}
    names_prev  = {norm_name(b.name)   for b in map_prev.values()}

    returning: list[Buyer] = []
    prospects: list[Buyer] = []
    for _k, b in map_prev.items():
        e = norm_email(b.email); p = norm_phone(b.phone); n = norm_name(b.name)
        is_ret = (e and e in emails_cur) or (p and p in phones_cur) or (n and n in names_cur)
        if is_ret:
            for bc in map_cur.values():
                e2 = norm_email(bc.email); p2 = norm_phone(bc.phone); n2 = norm_name(bc.name)
                if (e and e2 and e == e2) or (p and p2 and p == p2) or n == n2:
                    b.tickets_cur = bc.tickets_cur
                    b.amount_cur  = bc.amount_cur
                    if not b.email and bc.email: b.email = bc.email
                    if not b.phone and bc.phone: b.phone = bc.phone
                    break
            returning.append(b)
        else:
            prospects.append(b)

    new_buyers: list[Buyer] = [
        b for _k, b in map_cur.items()
        if not (
            (norm_email(b.email) and norm_email(b.email) in emails_prev) or
            (norm_phone(b.phone) and norm_phone(b.phone) in phones_prev) or
            (norm_name(b.name)  and norm_name(b.name)  in names_prev)
        )
    ]

    returning.sort(key=lambda b: b.amount_cur,  reverse=True)
    prospects.sort(key=lambda b: b.amount_prev, reverse=True)
    new_buyers.sort(key=lambda b: b.amount_cur, reverse=True)

    # ── Cumulative chart (MM-DD aligned) ──────────────────────────────────────
    master_labels: list[str] = []
    _d = date(2001, 1, 1)
    while _d.year == 2001:
        master_labels.append(_d.strftime("%m-%d"))
        _d += timedelta(days=1)
    today_mmdd = TODAY.strftime("%m-%d")

    def build_cumul(daily: dict, year: int, cap: str | None) -> list:
        out = []; running = 0.0
        for mmdd in master_labels:
            if cap and mmdd > cap:
                out.append(None); continue
            running += daily.get(f"{year}-{mmdd}", 0.0)
            out.append(round(running, 2))
        return out

    chart_prev = build_cumul(daily_prev, PREV_YEAR, None)
    chart_cur  = build_cumul(daily_cur,  CURRENT_YEAR, today_mmdd)

    # ── HTML table rows ───────────────────────────────────────────────────────
    def _email_link(e):
        e = esc(e)
        return f'<a href="mailto:{e}">{e}</a>' if e else ""

    def ret_row(b: Buyer) -> str:
        n, e, p = esc(b.name), b.email, esc(b.phone)
        return (
            f'<tr data-search="{esc(b.name)} {esc(b.email)} {p}">'
            f'<td>{esc(b.name)}</td><td>{_email_link(e)}</td><td>{p}</td>'
            f'<td class="r">{b.tickets_prev or "—"}</td>'
            f'<td class="r amt">${b.amount_prev:,.0f}</td>'
            f'<td class="r">{b.tickets_cur or "—"}</td>'
            f'<td class="r amt hi">${b.amount_cur:,.0f}</td>'
            f'</tr>'
        )

    def pro_row(b: Buyer) -> str:
        n, e, p = esc(b.name), b.email, esc(b.phone)
        return (
            f'<tr data-search="{esc(b.name)} {esc(b.email)} {p}">'
            f'<td>{esc(b.name)}</td><td>{_email_link(e)}</td><td>{p}</td>'
            f'<td class="r">{b.tickets_prev or "—"}</td>'
            f'<td class="r amt">${b.amount_prev:,.0f}</td>'
            f'</tr>'
        )

    def new_row(b: Buyer) -> str:
        n, e, p = esc(b.name), b.email, esc(b.phone)
        return (
            f'<tr data-search="{esc(b.name)} {esc(b.email)} {p}">'
            f'<td>{esc(b.name)}</td><td>{_email_link(e)}</td><td>{p}</td>'
            f'<td class="r">{b.tickets_cur or "—"}</td>'
            f'<td class="r amt hi">${b.amount_cur:,.0f}</td>'
            f'</tr>'
        )

    EMPTY_RET = f'<tr><td colspan="7" class="empty">No returning buyers yet.</td></tr>'
    EMPTY_PRO = f'<tr><td colspan="5" class="empty">All {PREV_YEAR} buyers are already in {CURRENT_YEAR}!</td></tr>'
    EMPTY_NEW = f'<tr><td colspan="5" class="empty">No first-time {CURRENT_YEAR} buyers yet.</td></tr>'

    ret_rate = round(len(returning) / len(map_prev) * 100, 1) if map_prev else 0.0
    pct_diff_raw = round((total_raised - todate_prev_amt) / todate_prev_amt * 100, 1) if todate_prev_amt else 0.0

    return {
        # Current-year stats
        "total_raised":          total_raised,
        "total_tickets":         total_tickets,
        "buyer_count":           len(buyers_cur),
        "daily_labels":          sorted_days,
        "daily_values":          [daily_totals[d] for d in sorted_days],
        "tier_labels":           [t[0] for t in tiers],
        "tier_values":           [t[1] for t in tiers],
        "top5":                  top5,
        "goal":                  GOAL,
        "pct":                   min(100, round(total_raised / GOAL * 100, 1)),
        "year":                  CURRENT_YEAR,
        "prev_year":             PREV_YEAR,
        "today":                 TODAY.strftime("%B %d, %Y"),
        "updated_at":            datetime.now(_TZ).strftime("%B %d, %Y %I:%M %p %Z"),
        # YoY
        "todate_prev_amt":       todate_prev_amt,
        "todate_prev_tix":       todate_prev_tix,
        "todate_prev_buyers":    len(todate_prev_keys),
        "pct_diff":              pct_diff_raw,
        "same_day_prev":         SAME_DAY_PREV.strftime("%b %d"),
        # Cumulative chart
        "chart_master_labels":   json.dumps(master_labels),
        "chart_prev":            json.dumps(chart_prev),
        "chart_cur":             json.dumps(chart_cur),
        "today_mmdd":            json.dumps(today_mmdd),
        # Retention tables
        "n_returning":           len(returning),
        "n_prospects":           len(prospects),
        "n_new":                 len(new_buyers),
        "ret_rate":              ret_rate,
        "rows_returning":        "".join(ret_row(b) for b in returning) or EMPTY_RET,
        "rows_prospects":        "".join(pro_row(b) for b in prospects) or EMPTY_PRO,
        "rows_new":              "".join(new_row(b) for b in new_buyers) or EMPTY_NEW,
    }

# ── HTML generation ───────────────────────────────────────────────────────────

def render_html(d: dict) -> str:
    top5_rows = "".join(
        f'<tr><td class="td-name">{esc(name)}</td><td class="td-amount">${amt:,.0f}</td></tr>'
        for name, amt in d["top5"]
    )
    arrow     = "▲" if d["pct_diff"] >= 0 else "▼"
    arrow_cls = "up" if d["pct_diff"] >= 0 else "dn"
    badge_cls = "badge-up" if d["pct_diff"] >= 0 else "badge-dn"
    sign      = "+" if d["pct_diff"] >= 0 else ""

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
      --grn:     #4ade80;
      --red:     #f87171;
      --text:    #f0e6ff;
      --muted:   #a78bca;
      --border:  rgba(192,132,252,.22);
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
    /* ── Tabs ── */
    .tabs {{
      max-width: 960px;
      margin: 0 auto 1.25rem;
      display: flex;
      gap: .5rem;
      flex-wrap: wrap;
    }}
    .tab-btn {{
      background: rgba(26,15,53,.8);
      border: 1px solid rgba(192,132,252,.25);
      border-radius: .6rem;
      color: var(--muted);
      font-size: .8rem;
      font-weight: 700;
      letter-spacing: .06em;
      padding: .45rem 1rem;
      cursor: pointer;
      transition: border-color .15s, color .15s;
    }}
    .tab-btn:hover {{ border-color: var(--cyan); color: var(--cyan); }}
    .tab-btn.active {{
      border-color: var(--cyan);
      color: var(--cyan);
      background: rgba(0,229,255,.08);
      text-shadow: 0 0 8px rgba(0,229,255,.4);
    }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}
    /* ── YoY card ── */
    .yoy-card {{
      max-width: 960px;
      margin: 0 auto 1.5rem;
      background: rgba(26,15,53,.8);
      border: 1px solid rgba(255,215,0,.28);
      border-radius: 1rem;
      padding: 1.4rem 1.75rem;
    }}
    .yoy-title {{
      font-size: .85rem; font-weight: 700;
      color: var(--gold); text-transform: uppercase;
      letter-spacing: .1em; margin-bottom: 1rem;
      text-shadow: 0 0 8px rgba(255,215,0,.5);
    }}
    .yoy-grid {{
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      gap: .75rem;
      align-items: center;
    }}
    .yoy-col {{ text-align: center; }}
    .yoy-yr  {{ font-size: .7rem; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); margin-bottom: .2rem; }}
    .yoy-val {{ font-size: 1.55rem; font-weight: 800; }}
    .yoy-sub {{ font-size: .72rem; color: var(--muted); margin-top: .15rem; }}
    .vs-col  {{ text-align: center; }}
    .vs-arrow {{ font-size: 1.5rem; font-weight: 900; }}
    .yoy-badge {{
      display: inline-block; font-size: .8rem; font-weight: 700;
      padding: .15rem .55rem; border-radius: 999px; margin-top: .3rem;
    }}
    .badge-up {{ background: rgba(74,222,128,.15); color: var(--grn); border: 1px solid rgba(74,222,128,.3); }}
    .badge-dn {{ background: rgba(248,113,113,.12); color: var(--red); border: 1px solid rgba(248,113,113,.3); }}
    .up {{ color: var(--grn); text-shadow: 0 0 8px rgba(74,222,128,.4); }}
    .dn {{ color: var(--red); text-shadow: 0 0 8px rgba(248,113,113,.4); }}
    /* ── Retention stat chips ── */
    .ret-grid {{
      max-width: 960px;
      margin: 0 auto 1.25rem;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: .9rem;
    }}
    .ret-card {{
      background: rgba(26,15,53,.8);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.1rem 1.25rem;
    }}
    .ret-label {{ font-size: .7rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: .3rem; }}
    .ret-val   {{ font-size: 1.7rem; font-weight: 800; line-height: 1.1; }}
    .ret-sub   {{ font-size: .68rem; color: var(--muted); margin-top: .25rem; }}
    .grn {{ color: var(--grn); text-shadow: 0 0 10px rgba(74,222,128,.55); }}
    /* ── Section panels ── */
    .section {{
      max-width: 960px;
      margin: 0 auto 1.5rem;
      background: rgba(26,15,53,.8);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.4rem 1.75rem;
    }}
    .sec-hdr {{
      display: flex; align-items: baseline; gap: .6rem; margin-bottom: .75rem;
    }}
    .sec-title {{
      font-size: .78rem; text-transform: uppercase;
      letter-spacing: .1em; color: var(--muted);
    }}
    .badge-count {{
      font-size: .72rem; font-weight: 700;
      padding: .1rem .45rem; border-radius: 999px;
      background: rgba(192,132,252,.18);
      color: var(--purple); border: 1px solid rgba(192,132,252,.3);
    }}
    .sec-desc {{ font-size: .78rem; color: var(--muted); margin-bottom: .85rem; }}
    .search-wrap {{ margin-bottom: .85rem; }}
    .search-wrap input {{
      width: 100%; max-width: 360px;
      background: rgba(255,255,255,.05);
      border: 1px solid rgba(192,132,252,.3);
      border-radius: .5rem;
      color: var(--text); font-size: .85rem;
      padding: .38rem .7rem; outline: none;
    }}
    .search-wrap input::placeholder {{ color: var(--muted); }}
    .search-wrap input:focus {{ border-color: var(--cyan); }}
    /* ── Retention tables ── */
    .tbl-wrap {{ overflow-x: auto; }}
    .ret-tbl {{ width: 100%; border-collapse: collapse; font-size: .855rem; min-width: 480px; }}
    .ret-tbl thead tr {{ border-bottom: 1px solid rgba(192,132,252,.3); }}
    .ret-tbl th {{
      padding: .45rem .45rem; text-align: left;
      font-size: .68rem; text-transform: uppercase;
      letter-spacing: .08em; color: var(--muted); white-space: nowrap;
    }}
    .ret-tbl th.r, .ret-tbl td.r {{ text-align: right; }}
    .ret-tbl tbody tr {{ border-bottom: 1px solid rgba(192,132,252,.08); transition: background .15s; }}
    .ret-tbl tbody tr:hover {{ background: rgba(192,132,252,.08); }}
    .ret-tbl tbody tr.hidden {{ display: none; }}
    .ret-tbl td {{ padding: .5rem .45rem; }}
    .ret-tbl td a {{ color: var(--cyan); text-decoration: none; font-size: .78rem; }}
    .ret-tbl td a:hover {{ text-decoration: underline; }}
    .ret-tbl td.amt {{ font-weight: 700; color: var(--muted); }}
    .ret-tbl td.hi  {{ color: var(--cyan); text-shadow: 0 0 8px rgba(0,229,255,.4); font-weight: 700; }}
    .ret-tbl td.empty {{ text-align: center; color: var(--muted); padding: 1.5rem; font-style: italic; }}
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

  <!-- Tab navigation -->
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('dashboard', this)">📊 Dashboard</button>
    <button class="tab-btn" onclick="switchTab('retention', this)">🔄 Retention &amp; YoY</button>
  </div>

  <!-- ═══════════════════════════════════════════════ DASHBOARD TAB ══ -->
  <div id="tab-dashboard" class="tab-panel active">

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

  </div><!-- /#tab-dashboard -->

  <!-- ═══════════════════════════════════════════ RETENTION TAB ══ -->
  <div id="tab-retention" class="tab-panel">

    <!-- Retention stat chips -->
    <div class="ret-grid">
      <div class="ret-card">
        <div class="ret-label">🎟 {d['year']} Buyers</div>
        <div class="ret-val cyan">{d['buyer_count']}</div>
      </div>
      <div class="ret-card">
        <div class="ret-label">🎟 {d['prev_year']} Buyers</div>
        <div class="ret-val purp">{d['n_returning'] + d['n_prospects']}</div>
      </div>
      <div class="ret-card">
        <div class="ret-label">🔄 Returning</div>
        <div class="ret-val grn">{d['n_returning']}</div>
        <div class="ret-sub">Retention: {d['ret_rate']}%</div>
      </div>
      <div class="ret-card">
        <div class="ret-label">📢 Prospects</div>
        <div class="ret-val gold">{d['n_prospects']}</div>
        <div class="ret-sub">{d['prev_year']} buyers not yet in {d['year']}</div>
      </div>
      <div class="ret-card">
        <div class="ret-label">✨ New Buyers</div>
        <div class="ret-val pink">{d['n_new']}</div>
        <div class="ret-sub">First-timers in {d['year']}</div>
      </div>
    </div>

    <!-- YoY comparison -->
    <div class="yoy-card">
      <div class="yoy-title">📊 Year-over-Year — through {d['today']} vs same date in {d['prev_year']}</div>
      <div class="yoy-grid">
        <div class="yoy-col">
          <div class="yoy-yr">{d['prev_year']} (through {d['same_day_prev']})</div>
          <div class="yoy-val purp">${d['todate_prev_amt']:,.0f}</div>
          <div class="yoy-sub">{d['todate_prev_tix']:,} tickets · {d['todate_prev_buyers']} buyers</div>
        </div>
        <div class="vs-col">
          <div class="vs-arrow {arrow_cls}">{arrow}</div>
          <div class="yoy-badge {badge_cls}">{sign}{d['pct_diff']}%</div>
        </div>
        <div class="yoy-col">
          <div class="yoy-yr">{d['year']} (to date)</div>
          <div class="yoy-val cyan">${d['total_raised']:,.0f}</div>
          <div class="yoy-sub">{d['total_tickets']:,} tickets · {d['buyer_count']} buyers</div>
        </div>
      </div>
    </div>

    <!-- Cumulative line chart -->
    <div class="chart-card" style="max-width:960px;margin:0 auto 1.5rem">
      <div class="chart-title">📈 Cumulative Sales — {d['prev_year']} (full year) vs {d['year']} (to date)</div>
      <canvas id="lineChart" style="max-height:360px"></canvas>
    </div>

    <!-- Returning buyers -->
    <div class="section">
      <div class="sec-hdr">
        <span class="sec-title">🔄 Returning Buyers</span>
        <span class="badge-count">{d['n_returning']}</span>
      </div>
      <p class="sec-desc">Bought tickets in both {d['prev_year']} and {d['year']}.</p>
      <div class="search-wrap"><input type="text" placeholder="Search name, email, phone…" oninput="filterTable('tbl-ret',this.value)" /></div>
      <div class="tbl-wrap">
        <table id="tbl-ret" class="ret-tbl">
          <thead><tr>
            <th>Name</th><th>Email</th><th>Phone</th>
            <th class="r">{d['prev_year']} Tix</th><th class="r">{d['prev_year']} Paid</th>
            <th class="r">{d['year']} Tix</th><th class="r">{d['year']} Paid</th>
          </tr></thead>
          <tbody>{d['rows_returning']}</tbody>
        </table>
      </div>
    </div>

    <!-- Prospects -->
    <div class="section">
      <div class="sec-hdr">
        <span class="sec-title">📢 Prospects — Solicit These Buyers</span>
        <span class="badge-count">{d['n_prospects']}</span>
      </div>
      <p class="sec-desc">
        Bought in {d['prev_year']} but <strong style="color:var(--gold)">not yet</strong> seen in {d['year']}.
        Sorted by {d['prev_year']} spend — highest value first.
      </p>
      <div class="search-wrap"><input type="text" placeholder="Search name, email, phone…" oninput="filterTable('tbl-pro',this.value)" /></div>
      <div class="tbl-wrap">
        <table id="tbl-pro" class="ret-tbl">
          <thead><tr>
            <th>Name</th><th>Email</th><th>Phone</th>
            <th class="r">{d['prev_year']} Tix</th><th class="r">{d['prev_year']} Paid</th>
          </tr></thead>
          <tbody>{d['rows_prospects']}</tbody>
        </table>
      </div>
    </div>

    <!-- New buyers -->
    <div class="section">
      <div class="sec-hdr">
        <span class="sec-title">✨ New {d['year']} Buyers (First-Timers)</span>
        <span class="badge-count">{d['n_new']}</span>
      </div>
      <p class="sec-desc">Purchased in {d['year']} with no record found in {d['prev_year']}.</p>
      <div class="search-wrap"><input type="text" placeholder="Search name, email, phone…" oninput="filterTable('tbl-new',this.value)" /></div>
      <div class="tbl-wrap">
        <table id="tbl-new" class="ret-tbl">
          <thead><tr>
            <th>Name</th><th>Email</th><th>Phone</th>
            <th class="r">{d['year']} Tix</th><th class="r">{d['year']} Paid</th>
          </tr></thead>
          <tbody>{d['rows_new']}</tbody>
        </table>
      </div>
    </div>

  </div><!-- /#tab-retention -->

  <div class="footer">&copy; {d['year']} Team Sir Pork a Lot &mdash; Hogs for the Cause</div>

  <script>
    const CYAN   = "#00e5ff";
    const PINK   = "#ff00cc";
    const GOLD   = "#ffd700";
    const PURPLE = "#c084fc";
    const GREEN  = "#4ade80";

    // ── Tab switching ────────────────────────────────────────────────────
    function switchTab(name, btn) {{
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.getElementById('tab-' + name).classList.add('active');
      btn.classList.add('active');
    }}

    // ── Table search ─────────────────────────────────────────────────────
    function filterTable(tableId, query) {{
      const q = query.toLowerCase().trim();
      document.querySelectorAll('#' + tableId + ' tbody tr').forEach(tr => {{
        const s = (tr.dataset.search || tr.innerText).toLowerCase();
        tr.classList.toggle('hidden', q.length > 0 && !s.includes(q));
      }});
    }}

    // ── Cumulative line chart ─────────────────────────────────────────────
    const MASTER_LABELS = {d['chart_master_labels']};
    const DATA_PREV     = {d['chart_prev']};
    const DATA_CUR      = {d['chart_cur']};
    const TODAY_MMDD    = {d['today_mmdd']};
    const tickLabels    = MASTER_LABELS.map((l, i) => (i % 14 === 0 ? l : ""));

    new Chart(document.getElementById("lineChart"), {{
      type: "line",
      data: {{
        labels: MASTER_LABELS,
        datasets: [
          {{
            label: "{d['prev_year']} Cumulative ($)",
            data: DATA_PREV,
            borderColor: PURPLE, backgroundColor: "rgba(192,132,252,.07)",
            borderWidth: 2, pointRadius: 0, tension: 0.3, fill: false, spanGaps: false,
          }},
          {{
            label: "{d['year']} Cumulative ($)",
            data: DATA_CUR,
            borderColor: CYAN, backgroundColor: "rgba(0,229,255,.07)",
            borderWidth: 2.5, pointRadius: 0, tension: 0.3, fill: false, spanGaps: false,
          }},
          {{
            label: "Today",
            data: MASTER_LABELS.map((l, i) => {{
              if (l !== TODAY_MMDD) return null;
              return Math.max(DATA_PREV[i] || 0, DATA_CUR[i] || 0) * 1.05;
            }}),
            borderColor: "rgba(255,215,0,.7)", borderWidth: 1.5,
            borderDash: [4,4], pointRadius: 6, pointStyle: "line",
            pointBorderColor: GOLD, showLine: false, spanGaps: false,
          }},
        ],
      }},
      options: {{
        responsive: true,
        interaction: {{ mode: "index", intersect: false }},
        plugins: {{
          legend: {{ position: "top", labels: {{ color: "#a78bca", font: {{ size: 11 }}, padding: 16 }} }},
          tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ": $" + (ctx.parsed.y||0).toLocaleString() }} }},
        }},
        scales: {{
          x: {{
            ticks: {{ color: "#a78bca", maxRotation: 45, callback: (v,i) => tickLabels[i] }},
            grid:  {{ color: "rgba(192,132,252,.08)" }},
          }},
          y: {{
            ticks: {{ color: "#a78bca", callback: v => "$" + v.toLocaleString() }},
            grid:  {{ color: "rgba(192,132,252,.08)" }},
          }},
        }},
      }},
    }});

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

    print("Fetching all list items (all years)...")
    all_items = get_list_items(token, site_id)

    print(f"Loading {PREV_YEAR} CSV...")
    csv_rows = load_csv_prev()

    print("Processing data...")
    data = process(all_items, csv_rows)
    print(
        f"  {CURRENT_YEAR}: ${data['total_raised']:,.0f} raised  "
        f"({data['n_returning']} returning, {data['n_prospects']} prospects, {data['n_new']} new)"
    )

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
