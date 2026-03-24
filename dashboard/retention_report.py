"""
dashboard/retention_report.py

Generates a self-contained HTML retention & year-over-year comparison report
and writes it to dashboard/dist/retention.html.

What it shows:
  • Summary stats — 2026 buyers, 2025 buyers, returning, prospects, new
  • Year-over-year "to same date" comparison (revenue, tickets, buyers)
  • Cumulative sales line chart: full 2025 year vs 2026 up to today
  • Returning buyers table   — bought in both 2025 and 2026
  • Prospects table          — bought in 2025, NOT yet seen in 2026 (solicit these)
  • New 2026 buyers table    — first-time buyers this year

Matching logic (any of these triggers a "returning" match):
  1. Normalised email  (lowercase, stripped)
  2. Normalised phone  (digits-only, last 10)
  3. Normalised name   (lowercase, collapsed whitespace)

Data sources:
  1. SharePoint list via Microsoft Graph API  — dated entries for BOTH 2025 and 2026
  2. Local CSV  "Hogs for the Cause 2025 Raffle.csv"  — 2025 names/emails/phones

Required environment variables:
  AZURE_TENANT_ID        Azure AD tenant
  AZURE_CLIENT_ID        App registration client ID
  AZURE_CLIENT_SECRET    App registration secret
  SHAREPOINT_LIST_ID     GUID of the SharePoint list

Optional environment variables:
  SHAREPOINT_HOSTNAME    (default: kingsofcode.sharepoint.com)
  SHAREPOINT_SITE_PATH   (default: /sites/StevieCopilot)
  GOAL_AMOUNT            (default: 30000)
"""

import csv
import html as html_lib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

# ── Config ────────────────────────────────────────────────────────────────────

TENANT_ID     = os.environ["AZURE_TENANT_ID"]
CLIENT_ID     = os.environ["AZURE_CLIENT_ID"]
CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]
SP_HOSTNAME   = os.environ.get("SHAREPOINT_HOSTNAME", "kingsofcode.sharepoint.com")
SP_SITE_PATH  = os.environ.get("SHAREPOINT_SITE_PATH", "/sites/StevieCopilot")
LIST_ID       = os.environ["SHAREPOINT_LIST_ID"]
GOAL          = int(os.environ.get("GOAL_AMOUNT", "30000"))

_TZ           = ZoneInfo("America/Chicago")
TODAY         = datetime.now(_TZ).date()
CUR_YEAR      = TODAY.year         # 2026
PREV_YEAR     = CUR_YEAR - 1      # 2025
SAME_DAY_PREV = date(PREV_YEAR, TODAY.month, TODAY.day)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH    = os.path.normpath(
    os.path.join(_SCRIPT_DIR, "..", "Hogs for the Cause 2025 Raffle.csv")
)

# ── Normalisation helpers ─────────────────────────────────────────────────────

def norm_name(n: str) -> str:
    return " ".join(str(n or "").lower().split())

def norm_phone(p: str) -> str:
    digits = re.sub(r"\D", "", str(p or ""))
    return digits[-10:] if len(digits) >= 10 else digits

def norm_email(e: str) -> str:
    return str(e or "").lower().strip()

def esc(s: str) -> str:
    """HTML-escape a string so it is safe to embed in table cells."""
    return html_lib.escape(str(s or ""))

def fmt_usd(v: float) -> str:
    return f"${v:,.0f}"

def pct_arrow(new: float, old: float) -> tuple[str, str, float]:
    """Returns (arrow_char, css_class, pct_diff)."""
    if old == 0:
        return ("▲", "up", 0.0)
    diff = round((new - old) / old * 100, 1)
    return ("▲", "up", diff) if diff >= 0 else ("▼", "dn", diff)

# ── Auth / Graph ──────────────────────────────────────────────────────────────

def get_token() -> str:
    r = requests.post(
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
        data={
            "grant_type":    "client_credentials",
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope":         "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def graph_get(token: str, url: str) -> dict:
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    return r.json()


def get_site_id(token: str) -> str:
    return graph_get(
        token,
        f"https://graph.microsoft.com/v1.0/sites/{SP_HOSTNAME}:{SP_SITE_PATH}",
    )["id"]


def fetch_all_items(token: str, site_id: str) -> list[dict]:
    """Fetch every item from the SharePoint list (all years, paginated)."""
    url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{LIST_ID}/items"
        f"?$expand=fields&$top=999"
    )
    items: list[dict] = []
    while url:
        data = graph_get(token, url)
        items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    print(f"  Total SharePoint items fetched: {len(items)}")
    return items

# ── CSV loader ────────────────────────────────────────────────────────────────

def load_csv_2025() -> list[dict]:
    """Read the 2025 attendee CSV (Name, Email Address, Phone Number)."""
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
    print(f"  CSV 2025 rows: {len(rows)}")
    return rows

# ── Buyer data class ──────────────────────────────────────────────────────────

class Buyer:
    __slots__ = (
        "name", "email", "phone",
        "tickets_2025", "amount_2025",
        "tickets_2026", "amount_2026",
    )

    def __init__(self, name="", email="", phone=""):
        self.name         = name
        self.email        = email
        self.phone        = phone
        self.tickets_2025 = 0
        self.amount_2025  = 0.0
        self.tickets_2026 = 0
        self.amount_2026  = 0.0

    # ── HTML row renderers ────────────────────────────────────────────────────

    def _base(self) -> tuple[str, str, str]:
        return esc(self.name), esc(self.email), esc(self.phone)

    def row_returning(self) -> str:
        n, e, p = self._base()
        email_link = f'<a href="mailto:{e}">{e}</a>' if self.email else ""
        return (
            f'<tr data-search="{n} {e} {p}">'
            f'<td>{n}</td>'
            f'<td>{email_link}</td>'
            f'<td>{p}</td>'
            f'<td class="r">{self.tickets_2025 or "—"}</td>'
            f'<td class="r amt">{fmt_usd(self.amount_2025) if self.amount_2025 else "—"}</td>'
            f'<td class="r">{self.tickets_2026 or "—"}</td>'
            f'<td class="r amt hi">{fmt_usd(self.amount_2026) if self.amount_2026 else "—"}</td>'
            f'</tr>'
        )

    def row_prospect(self) -> str:
        n, e, p = self._base()
        email_link = f'<a href="mailto:{e}">{e}</a>' if self.email else ""
        return (
            f'<tr data-search="{n} {e} {p}">'
            f'<td>{n}</td>'
            f'<td>{email_link}</td>'
            f'<td>{p}</td>'
            f'<td class="r">{self.tickets_2025 or "—"}</td>'
            f'<td class="r amt">{fmt_usd(self.amount_2025) if self.amount_2025 else "?"}</td>'
            f'</tr>'
        )

    def row_new(self) -> str:
        n, e, p = self._base()
        email_link = f'<a href="mailto:{e}">{e}</a>' if self.email else ""
        return (
            f'<tr data-search="{n} {e} {p}">'
            f'<td>{n}</td>'
            f'<td>{email_link}</td>'
            f'<td>{p}</td>'
            f'<td class="r">{self.tickets_2026 or "—"}</td>'
            f'<td class="r amt hi">{fmt_usd(self.amount_2026) if self.amount_2026 else "—"}</td>'
            f'</tr>'
        )


# ── Core processing ───────────────────────────────────────────────────────────

def process_data(sp_items: list[dict], csv_rows: list[dict]) -> dict:

    # ── 1. Bucket SharePoint items by year (Hogs_For_the_Cause only) ──────────
    sp25: list[dict] = []
    sp26: list[dict] = []
    # Debug: show all unique RaffleName values before filtering
    unique_raffles = {(item.get("fields") or {}).get("RaffleName") for item in sp_items}
    print(f"  Unique RaffleName values in list: {sorted(str(r) for r in unique_raffles)}")
    for item in sp_items:
        f      = item.get("fields", {})
        raffle = (f.get("RaffleName") or "").strip()
        # Case-insensitive match to handle any casing in SharePoint
        if raffle.lower() != "hogs_for_the_cause":
            continue
        yr = (f.get("SubmissionDate") or "")[:4]
        if yr == str(CUR_YEAR):
            sp26.append(f)
        elif yr == str(PREV_YEAR):
            sp25.append(f)
    print(f"  SharePoint — {PREV_YEAR}: {len(sp25)},  {CUR_YEAR}: {len(sp26)}")

    # ── Helper: choose the best primary key for a buyer record ────────────────
    def _key(email: str, phone: str, name: str) -> str:
        e = norm_email(email)
        p = norm_phone(phone)
        n = norm_name(name)
        return e if e else (p if p else n)

    # ── 2. Build 2026 buyer map ───────────────────────────────────────────────
    map26: dict[str, Buyer] = {}
    daily26: dict[str, float] = defaultdict(float)
    total26_amount  = 0.0
    total26_tickets = 0

    for f in sp26:
        name    = str(f.get("Person")            or "Unknown").strip()
        amount  = float(f.get("TotalPaid")        or 0)
        tickets = int(f.get("NumberofChances")    or 0)
        email   = str(f.get("Email")              or "").strip()
        phone   = str(f.get("Phone")              or "").strip()
        day     = (f.get("SubmissionDate")         or "")[:10]

        total26_amount  += amount
        total26_tickets += tickets
        if day:
            daily26[day] += amount

        k = _key(email, phone, name)
        if k not in map26:
            map26[k] = Buyer(name=name, email=email, phone=phone)
        map26[k].tickets_2026 += tickets
        map26[k].amount_2026  += amount

    # ── 3. Build 2025 buyer map from SharePoint ───────────────────────────────
    map25: dict[str, Buyer] = {}
    daily25: dict[str, float] = defaultdict(float)
    total25_amount     = 0.0
    total25_tickets    = 0
    todate25_amount    = 0.0
    todate25_tickets   = 0
    todate25_keys: set[str] = set()

    for f in sp25:
        name    = str(f.get("Person")            or "Unknown").strip()
        amount  = float(f.get("TotalPaid")        or 0)
        tickets = int(f.get("NumberofChances")    or 0)
        email   = str(f.get("Email")              or "").strip()
        phone   = str(f.get("Phone")              or "").strip()
        day     = (f.get("SubmissionDate")         or "")[:10]

        total25_amount  += amount
        total25_tickets += tickets
        if day:
            daily25[day] += amount
            if day <= str(SAME_DAY_PREV):
                todate25_amount  += amount
                todate25_tickets += tickets

        k = _key(email, phone, name)
        if day and day <= str(SAME_DAY_PREV):
            todate25_keys.add(k)

        if k not in map25:
            map25[k] = Buyer(name=name, email=email, phone=phone)
        map25[k].tickets_2025 += tickets
        map25[k].amount_2025  += amount

    # ── 4. Supplement 2025 map with CSV entries ───────────────────────────────
    for row in csv_rows:
        e_n = norm_email(row["email"])
        p_n = norm_phone(row["phone"])
        n_n = norm_name(row["name"])

        # Try to find an existing 2025 entry to enrich with email/phone
        matched_key: str | None = None
        if e_n and e_n in map25:
            matched_key = e_n
        elif p_n and p_n in map25:
            matched_key = p_n
        else:
            for k, b in map25.items():
                if norm_name(b.name) == n_n:
                    matched_key = k
                    break

        if matched_key:
            b = map25[matched_key]
            if not b.email and row["email"]:
                b.email = row["email"]
            if not b.phone and row["phone"]:
                b.phone = row["phone"]
        else:
            # CSV-only buyer (no corresponding SharePoint record)
            k = e_n or p_n or n_n
            if k and k not in map25:
                map25[k] = Buyer(
                    name=row["name"],
                    email=row["email"],
                    phone=row["phone"],
                )

    print(f"  Unique buyers — {PREV_YEAR}: {len(map25)},  {CUR_YEAR}: {len(map26)}")

    # ── 5. Cross-reference: returning vs. prospects ───────────────────────────
    emails26 = {norm_email(b.email)  for b in map26.values() if b.email}
    phones26 = {norm_phone(b.phone)  for b in map26.values() if b.phone}
    names26  = {norm_name(b.name)    for b in map26.values()}

    returning: list[Buyer] = []
    prospects: list[Buyer] = []

    for _k, b25 in map25.items():
        e = norm_email(b25.email)
        p = norm_phone(b25.phone)
        n = norm_name(b25.name)
        is_returning = (
            (e and e in emails26) or
            (p and p in phones26) or
            (n and n in names26)
        )
        if is_returning:
            # Merge 2026 amounts onto the combined record
            for b26 in map26.values():
                e2 = norm_email(b26.email)
                p2 = norm_phone(b26.phone)
                n2 = norm_name(b26.name)
                if (e and e2 and e == e2) or (p and p2 and p == p2) or n == n2:
                    b25.tickets_2026 = b26.tickets_2026
                    b25.amount_2026  = b26.amount_2026
                    if not b25.email and b26.email:
                        b25.email = b26.email
                    if not b25.phone and b26.phone:
                        b25.phone = b26.phone
                    break
            returning.append(b25)
        else:
            prospects.append(b25)

    # New 2026 buyers (not matched in 2025 at all)
    emails25 = {norm_email(b.email)  for b in map25.values() if b.email}
    phones25 = {norm_phone(b.phone)  for b in map25.values() if b.phone}
    names25  = {norm_name(b.name)    for b in map25.values()}

    new_buyers: list[Buyer] = []
    for _k, b26 in map26.items():
        e = norm_email(b26.email)
        p = norm_phone(b26.phone)
        n = norm_name(b26.name)
        if not (
            (e and e in emails25) or
            (p and p in phones25) or
            (n and n in names25)
        ):
            new_buyers.append(b26)

    # Sort tables: returning/new by 2026 spend desc; prospects by 2025 spend desc
    returning.sort(key=lambda b: b.amount_2026,  reverse=True)
    prospects.sort(key=lambda b: b.amount_2025,  reverse=True)
    new_buyers.sort(key=lambda b: b.amount_2026, reverse=True)

    # ── 6. Cumulative chart data (both years aligned on MM-DD axis) ───────────
    # Generate 365 MM-DD labels using a reference non-leap year
    master_labels: list[str] = []
    _d = date(2001, 1, 1)
    while _d.year == 2001:
        master_labels.append(_d.strftime("%m-%d"))
        _d += timedelta(days=1)

    today_mmdd = TODAY.strftime("%m-%d")

    def build_cumul(daily: dict[str, float], year: int, cap: str | None) -> list:
        out: list = []
        running = 0.0
        for mmdd in master_labels:
            if cap and mmdd > cap:
                out.append(None)
                continue
            day_str = f"{year}-{mmdd}"
            running += daily.get(day_str, 0.0)
            out.append(round(running, 2))
        return out

    chart_2025 = build_cumul(daily25, PREV_YEAR, None)
    chart_2026 = build_cumul(daily26, CUR_YEAR, today_mmdd)

    # ── 7. Assemble output dict ───────────────────────────────────────────────
    return {
        "year":        CUR_YEAR,
        "prev_year":   PREV_YEAR,
        "today":       TODAY.strftime("%B %d, %Y"),
        "updated_at":  datetime.now(_TZ).strftime("%B %d, %Y %I:%M %p %Z"),
        "goal":        GOAL,
        # Buyer counts
        "n_2026":      len(map26),
        "n_2025":      len(map25),
        "n_returning": len(returning),
        "n_prospects": len(prospects),
        "n_new":       len(new_buyers),
        # Revenue / tickets
        "tot26_amt":   total26_amount,
        "tot26_tix":   total26_tickets,
        "tot25_amt":   todate25_amount,     # 2025 revenue through same calendar date
        "tot25_tix":   todate25_tickets,
        "tot25_buyers": len(todate25_keys),
        "tot25_full_amt": total25_amount,
        "tot25_full_tix": total25_tickets,
        # Chart (JSON strings, safe to embed directly)
        "chart_labels":   json.dumps(master_labels),
        "chart_2025":     json.dumps(chart_2025),
        "chart_2026":     json.dumps(chart_2026),
        "today_mmdd":     json.dumps(today_mmdd),
        # Table rows (pre-rendered HTML)
        "rows_returning": "".join(b.row_returning() for b in returning)
            or '<tr><td colspan="7" class="empty">No returning buyers found yet.</td></tr>',
        "rows_prospects": "".join(b.row_prospect() for b in prospects)
            or '<tr><td colspan="5" class="empty">All 2025 buyers have already purchased in 2026!</td></tr>',
        "rows_new": "".join(b.row_new() for b in new_buyers)
            or '<tr><td colspan="5" class="empty">No first-time 2026 buyers yet.</td></tr>',
    }


# ── HTML rendering ────────────────────────────────────────────────────────────

def render_html(d: dict) -> str:
    pct_goal = min(100, round(d["tot26_amt"] / d["goal"] * 100, 1)) if d["goal"] else 0

    arrow, arrow_cls, pct_diff = pct_arrow(d["tot26_amt"], d["tot25_amt"])

    # YoY retention rate
    ret_rate = (
        round(d["n_returning"] / d["n_2025"] * 100, 1) if d["n_2025"] > 0 else 0.0
    )

    def _stat_card(label: str, value: str, color_cls: str, sub: str = "") -> str:
        sub_html = f'<div class="card-sub">{sub}</div>' if sub else ""
        return (
            f'<div class="card">'
            f'<div class="card-label">{label}</div>'
            f'<div class="card-value {color_cls}">{value}</div>'
            f'{sub_html}'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Sir Pork-a-Lot · Retention &amp; YoY Report {d['year']}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg:     #0f0820;
      --card:   #1a0f35;
      --cyan:   #00e5ff;
      --pink:   #ff00cc;
      --gold:   #ffd700;
      --purp:   #c084fc;
      --grn:    #4ade80;
      --red:    #f87171;
      --text:   #f0e6ff;
      --muted:  #a78bca;
      --border: rgba(192,132,252,.22);
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: radial-gradient(ellipse at 50% 0%, rgba(160,80,255,.22) 0%, transparent 55%),
                  linear-gradient(180deg,#0f0820 0%,#1a0d35 100%);
      min-height: 100vh;
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      padding: 2rem 1rem 4rem;
    }}

    /* ── Header ───────────────────────────────────────────── */
    .header {{
      text-align: center;
      margin-bottom: 2.5rem;
    }}
    .header img {{
      width: 120px;
      mix-blend-mode: screen;
      filter: drop-shadow(0 0 24px rgba(255,0,204,.6));
      margin-bottom: .75rem;
    }}
    .header h1 {{
      font-size: 1.4rem;
      font-weight: 800;
      letter-spacing: .12em;
      text-transform: uppercase;
      color: var(--purp);
    }}
    .header .sub {{
      font-size: .85rem;
      color: var(--muted);
      margin-top: .25rem;
    }}
    .divider {{
      height: 1px;
      background: linear-gradient(90deg,transparent,var(--pink),var(--cyan),var(--pink),transparent);
      box-shadow: 0 0 8px rgba(255,0,204,.5);
      max-width: 360px;
      margin: .75rem auto 0;
    }}

    /* ── Shared layout ────────────────────────────────────── */
    .wrap {{ max-width: 1060px; margin: 0 auto; }}

    /* ── Stat cards ───────────────────────────────────────── */
    .stat-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }}
    .card {{
      background: rgba(26,15,53,.8);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.25rem 1.4rem;
    }}
    .card-label {{
      font-size: .72rem;
      text-transform: uppercase;
      letter-spacing: .08em;
      color: var(--muted);
      margin-bottom: .35rem;
    }}
    .card-value {{
      font-size: 1.9rem;
      font-weight: 800;
      line-height: 1.1;
    }}
    .card-sub {{
      font-size: .72rem;
      color: var(--muted);
      margin-top: .3rem;
    }}
    .cyan  {{ color: var(--cyan); text-shadow: 0 0 10px rgba(0,229,255,.55); }}
    .gold  {{ color: var(--gold); text-shadow: 0 0 10px rgba(255,215,0,.55); }}
    .pink  {{ color: var(--pink); text-shadow: 0 0 10px rgba(255,0,204,.55); }}
    .purp  {{ color: var(--purp); text-shadow: 0 0 10px rgba(192,132,252,.55); }}
    .grn   {{ color: var(--grn);  text-shadow: 0 0 10px rgba(74,222,128,.55); }}
    .up    {{ color: var(--grn); }}
    .dn    {{ color: var(--red); }}

    /* ── YoY comparison card ──────────────────────────────── */
    .yoy-card {{
      background: rgba(26,15,53,.8);
      border: 1px solid rgba(255,215,0,.28);
      border-radius: 1rem;
      padding: 1.4rem 1.75rem;
      margin-bottom: 1.5rem;
    }}
    .yoy-title {{
      font-size: .85rem;
      font-weight: 700;
      color: var(--gold);
      text-transform: uppercase;
      letter-spacing: .1em;
      margin-bottom: 1rem;
      text-shadow: 0 0 8px rgba(255,215,0,.5);
    }}
    .yoy-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
    }}
    .yoy-col {{ text-align: center; }}
    .yoy-yr  {{
      font-size: .7rem;
      text-transform: uppercase;
      letter-spacing: .1em;
      color: var(--muted);
      margin-bottom: .2rem;
    }}
    .yoy-val {{
      font-size: 1.55rem;
      font-weight: 800;
    }}
    .yoy-sub {{ font-size: .75rem; color: var(--muted); margin-top: .15rem; }}
    .vs-arrow {{
      font-size: 1.3rem;
      font-weight: 900;
      align-self: center;
      text-align: center;
    }}
    .yoy-badge {{
      display: inline-block;
      font-size: .8rem;
      font-weight: 700;
      padding: .15rem .55rem;
      border-radius: 999px;
      margin-top: .4rem;
    }}
    .badge-up {{ background: rgba(74,222,128,.15); color: var(--grn); border: 1px solid rgba(74,222,128,.3); }}
    .badge-dn {{ background: rgba(248,113,113,.12); color: var(--red); border: 1px solid rgba(248,113,113,.3); }}

    /* ── Goal bar ─────────────────────────────────────────── */
    .goal-card {{
      background: rgba(26,15,53,.8);
      border: 1px solid rgba(255,215,0,.28);
      border-radius: 1rem;
      padding: 1.25rem 1.75rem;
      margin-bottom: 1.5rem;
    }}
    .goal-hdr {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: .65rem;
    }}
    .goal-title {{ font-size: .9rem; font-weight: 700; color: var(--gold); text-shadow: 0 0 8px rgba(255,215,0,.5); }}
    .goal-pct   {{ font-size: 1.3rem; font-weight: 800; color: var(--gold); }}
    .bar-track  {{ background: rgba(255,255,255,.07); border-radius: 9999px; height: 16px; overflow: hidden; }}
    .bar-fill   {{
      height: 100%;
      border-radius: 9999px;
      background: linear-gradient(90deg,#cc00aa,#ff00cc,#ffd700);
      box-shadow: 0 0 14px rgba(255,0,204,.5);
      width: {pct_goal}%;
    }}
    .goal-sub {{
      display: flex;
      justify-content: space-between;
      font-size: .75rem;
      color: var(--muted);
      margin-top: .45rem;
    }}

    /* ── Chart card ───────────────────────────────────────── */
    .chart-card {{
      background: rgba(26,15,53,.8);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.4rem 1.75rem;
      margin-bottom: 1.5rem;
    }}
    .chart-title {{
      font-size: .78rem;
      text-transform: uppercase;
      letter-spacing: .1em;
      color: var(--muted);
      margin-bottom: 1rem;
    }}

    /* ── Section headers ──────────────────────────────────── */
    .section {{
      background: rgba(26,15,53,.8);
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.4rem 1.75rem;
      margin-bottom: 1.5rem;
    }}
    .section-header {{
      display: flex;
      align-items: baseline;
      gap: .75rem;
      margin-bottom: 1rem;
    }}
    .section-title {{
      font-size: .82rem;
      text-transform: uppercase;
      letter-spacing: .1em;
      color: var(--muted);
    }}
    .badge-count {{
      font-size: .75rem;
      font-weight: 700;
      padding: .1rem .45rem;
      border-radius: 999px;
      background: rgba(192,132,252,.18);
      color: var(--purp);
      border: 1px solid rgba(192,132,252,.3);
    }}

    /* ── Search input ─────────────────────────────────────── */
    .search-wrap {{ margin-bottom: .9rem; }}
    .search-wrap input {{
      width: 100%;
      max-width: 380px;
      background: rgba(255,255,255,.05);
      border: 1px solid rgba(192,132,252,.3);
      border-radius: .5rem;
      color: var(--text);
      font-size: .85rem;
      padding: .4rem .75rem;
      outline: none;
    }}
    .search-wrap input::placeholder {{ color: var(--muted); }}
    .search-wrap input:focus {{ border-color: var(--cyan); }}

    /* ── Tables ───────────────────────────────────────────── */
    .tbl-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: .875rem; min-width: 520px; }}
    thead tr {{ border-bottom: 1px solid rgba(192,132,252,.3); }}
    th {{
      padding: .5rem .5rem;
      text-align: left;
      font-size: .7rem;
      text-transform: uppercase;
      letter-spacing: .08em;
      color: var(--muted);
      white-space: nowrap;
    }}
    th.r, td.r {{ text-align: right; }}
    tbody tr {{
      border-bottom: 1px solid rgba(192,132,252,.08);
      transition: background .15s;
    }}
    tbody tr:hover {{ background: rgba(192,132,252,.08); }}
    tbody tr.hidden {{ display: none; }}
    td {{ padding: .55rem .5rem; }}
    td a {{ color: var(--cyan); text-decoration: none; font-size: .8rem; }}
    td a:hover {{ text-decoration: underline; }}
    td.amt {{ font-weight: 700; color: var(--muted); }}
    td.hi  {{ color: var(--cyan); text-shadow: 0 0 8px rgba(0,229,255,.4); }}
    td.empty {{
      text-align: center;
      color: var(--muted);
      padding: 1.5rem;
      font-style: italic;
    }}

    /* ── Footer ───────────────────────────────────────────── */
    .footer {{
      text-align: center;
      margin-top: 2rem;
      font-size: .72rem;
      color: rgba(167,139,202,.35);
    }}
  </style>
</head>
<body>

  <!-- ── Header ─────────────────────────────────────────────────────────── -->
  <div class="header">
    <img src="https://sirporkalot.vercel.app/Photo_2.jpeg" alt="Sir Pork-a-Lot" />
    <h1>Retention &amp; Year-over-Year Report</h1>
    <p class="sub">Hogs for the Cause · As of {d['today']} · Updated {d['updated_at']}</p>
    <div class="divider"></div>
  </div>

  <div class="wrap">

    <!-- ── Summary stat cards ──────────────────────────────────────────── -->
    <div class="stat-grid">
      {_stat_card("🎟 " + str(d['year']) + " Buyers",    str(d['n_2026']),      "cyan")}
      {_stat_card("🎟 " + str(d['prev_year']) + " Buyers",str(d['n_2025']),      "purp")}
      {_stat_card("🔄 Returning",  str(d['n_returning']), "grn",
                  f"Retention rate: {ret_rate}%")}
      {_stat_card("📢 Prospects",  str(d['n_prospects']), "gold",
                  f"2025 buyers not yet in {d['year']}")}
      {_stat_card("✨ New Buyers", str(d['n_new']),       "pink",
                  f"First-timers in {d['year']}")}
    </div>

    <!-- ── Goal progress bar ───────────────────────────────────────────── -->
    <div class="goal-card">
      <div class="goal-hdr">
        <span class="goal-title">🎯 {d['year']} Goal — ${d['goal']:,}</span>
        <span class="goal-pct">{pct_goal}%</span>
      </div>
      <div class="bar-track"><div class="bar-fill"></div></div>
      <div class="goal-sub">
        <span>{fmt_usd(d['tot26_amt'])} raised · {d['tot26_tix']:,} tickets sold</span>
        <span>{fmt_usd(d['goal'] - d['tot26_amt'])} to go</span>
      </div>
    </div>

    <!-- ── Year-over-year comparison ──────────────────────────────────── -->
    <div class="yoy-card">
      <div class="yoy-title">📊 Year-over-Year — through {d['today']} vs same date in {d['prev_year']}</div>
      <div class="yoy-grid">

        <div class="yoy-col">
          <div class="yoy-yr">{d['prev_year']} (through {SAME_DAY_PREV.strftime('%b %d')})</div>
          <div class="yoy-val purp">{fmt_usd(d['tot25_amt'])}</div>
          <div class="yoy-sub">{d['tot25_tix']:,} tickets · {d['tot25_buyers']} buyers</div>
        </div>

        <div class="vs-arrow">
          <div class="{arrow_cls}">{arrow}</div>
          <div class="yoy-badge {'badge-up' if arrow_cls == 'up' else 'badge-dn'}">
            {'+'if pct_diff >= 0 else ''}{pct_diff}%
          </div>
        </div>

        <div class="yoy-col">
          <div class="yoy-yr">{d['year']} (to date)</div>
          <div class="yoy-val cyan">{fmt_usd(d['tot26_amt'])}</div>
          <div class="yoy-sub">{d['tot26_tix']:,} tickets · {d['n_2026']} buyers</div>
        </div>

      </div>
    </div>

    <!-- ── Cumulative sales chart ──────────────────────────────────────── -->
    <div class="chart-card">
      <div class="chart-title">
        📈 Cumulative Sales Over Time — {d['prev_year']} (full year) vs {d['year']} (to date)
      </div>
      <canvas id="lineChart" style="max-height:380px"></canvas>
    </div>

    <!-- ── Returning buyers ─────────────────────────────────────────────── -->
    <div class="section">
      <div class="section-header">
        <span class="section-title">🔄 Returning Buyers</span>
        <span class="badge-count">{d['n_returning']}</span>
      </div>
      <p style="font-size:.8rem;color:var(--muted);margin-bottom:.9rem">
        Bought tickets in both {d['prev_year']} and {d['year']}.
      </p>
      <div class="search-wrap">
        <input type="text" placeholder="Search by name, email, or phone…"
               oninput="filterTable('tbl-ret', this.value)" />
      </div>
      <div class="tbl-wrap">
        <table id="tbl-ret">
          <thead>
            <tr>
              <th>Name</th><th>Email</th><th>Phone</th>
              <th class="r">{d['prev_year']} Tickets</th>
              <th class="r">{d['prev_year']} Paid</th>
              <th class="r">{d['year']} Tickets</th>
              <th class="r">{d['year']} Paid</th>
            </tr>
          </thead>
          <tbody>{d['rows_returning']}</tbody>
        </table>
      </div>
    </div>

    <!-- ── Prospects ──────────────────────────────────────────────────── -->
    <div class="section">
      <div class="section-header">
        <span class="section-title">📢 Prospects — Solicit These Buyers</span>
        <span class="badge-count">{d['n_prospects']}</span>
      </div>
      <p style="font-size:.8rem;color:var(--muted);margin-bottom:.9rem">
        Bought in {d['prev_year']} but <strong style="color:var(--gold)">not yet</strong>
        seen in {d['year']}. Sorted by {d['prev_year']} spend — highest value first.
      </p>
      <div class="search-wrap">
        <input type="text" placeholder="Search by name, email, or phone…"
               oninput="filterTable('tbl-pro', this.value)" />
      </div>
      <div class="tbl-wrap">
        <table id="tbl-pro">
          <thead>
            <tr>
              <th>Name</th><th>Email</th><th>Phone</th>
              <th class="r">{d['prev_year']} Tickets</th>
              <th class="r">{d['prev_year']} Paid</th>
            </tr>
          </thead>
          <tbody>{d['rows_prospects']}</tbody>
        </table>
      </div>
    </div>

    <!-- ── New 2026 buyers ────────────────────────────────────────────── -->
    <div class="section">
      <div class="section-header">
        <span class="section-title">✨ New {d['year']} Buyers (First-Timers)</span>
        <span class="badge-count">{d['n_new']}</span>
      </div>
      <p style="font-size:.8rem;color:var(--muted);margin-bottom:.9rem">
        Purchased in {d['year']} with no record found in {d['prev_year']}.
      </p>
      <div class="search-wrap">
        <input type="text" placeholder="Search by name, email, or phone…"
               oninput="filterTable('tbl-new', this.value)" />
      </div>
      <div class="tbl-wrap">
        <table id="tbl-new">
          <thead>
            <tr>
              <th>Name</th><th>Email</th><th>Phone</th>
              <th class="r">{d['year']} Tickets</th>
              <th class="r">{d['year']} Paid</th>
            </tr>
          </thead>
          <tbody>{d['rows_new']}</tbody>
        </table>
      </div>
    </div>

  </div><!-- /.wrap -->

  <div class="footer">&copy; {d['year']} Team Sir Pork-a-Lot &mdash; Hogs for the Cause</div>

  <script>
    /* ── Cumulative line chart ──────────────────────────────────────── */
    const LABELS = {d['chart_labels']};
    const DATA25 = {d['chart_2025']};
    const DATA26 = {d['chart_2026']};
    const TODAY_MMDD = {d['today_mmdd']};

    // Thin labels to show approx every 14 days on x-axis ticks
    const tickLabels = LABELS.map((l, i) => (i % 14 === 0 ? l : ""));

    new Chart(document.getElementById("lineChart"), {{
      type: "line",
      data: {{
        labels: LABELS,
        datasets: [
          {{
            label: "{d['prev_year']} Cumulative ($)",
            data: DATA25,
            borderColor: "#c084fc",
            backgroundColor: "rgba(192,132,252,.08)",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3,
            fill: false,
            spanGaps: false,
          }},
          {{
            label: "{d['year']} Cumulative ($)",
            data: DATA26,
            borderColor: "#00e5ff",
            backgroundColor: "rgba(0,229,255,.08)",
            borderWidth: 2.5,
            pointRadius: 0,
            tension: 0.3,
            fill: false,
            spanGaps: false,
          }},
          {{
            // "Today" vertical marker — single point at today's x position
            label: "Today",
            data: LABELS.map((l, i) => {{
              if (l !== TODAY_MMDD) return null;
              // use the larger of the two year values to make the marker visible
              const v25 = DATA25[i] || 0;
              const v26 = DATA26[i] || 0;
              return Math.max(v25, v26) * 1.05;
            }}),
            borderColor: "rgba(255,215,0,.7)",
            borderWidth: 1.5,
            borderDash: [4,4],
            pointRadius: 6,
            pointStyle: "line",
            pointBorderColor: "#ffd700",
            showLine: false,
            spanGaps: false,
          }},
        ],
      }},
      options: {{
        responsive: true,
        interaction: {{ mode: "index", intersect: false }},
        plugins: {{
          legend: {{
            position: "top",
            labels: {{ color: "#a78bca", font: {{ size: 11 }}, padding: 16 }},
          }},
          tooltip: {{
            callbacks: {{
              label: ctx => ctx.dataset.label + ": $" + (ctx.parsed.y || 0).toLocaleString(),
            }},
          }},
        }},
        scales: {{
          x: {{
            ticks: {{
              color: "#a78bca",
              maxRotation: 45,
              callback: (val, idx) => tickLabels[idx],
            }},
            grid: {{ color: "rgba(192,132,252,.08)" }},
          }},
          y: {{
            ticks: {{
              color: "#a78bca",
              callback: v => "$" + v.toLocaleString(),
            }},
            grid: {{ color: "rgba(192,132,252,.08)" }},
          }},
        }},
      }},
    }});

    /* ── Table search / filter ──────────────────────────────────────── */
    function filterTable(tableId, query) {{
      const q = query.toLowerCase().trim();
      document.querySelectorAll("#" + tableId + " tbody tr").forEach(tr => {{
        const searchVal = (tr.dataset.search || tr.innerText).toLowerCase();
        tr.classList.toggle("hidden", q.length > 0 && !searchVal.includes(q));
      }});
    }}
  </script>
</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("Authenticating to Microsoft Graph…")
    token = get_token()

    print("Resolving SharePoint site ID…")
    site_id = get_site_id(token)
    print(f"  Site ID: {site_id}")

    print("Fetching all SharePoint list items (all years)…")
    sp_items = fetch_all_items(token, site_id)

    print("Loading 2025 CSV…")
    csv_rows = load_csv_2025()

    print("Processing data…")
    d = process_data(sp_items, csv_rows)
    print(
        f"  {d['prev_year']} buyers: {d['n_2025']}  |  "
        f"{d['year']} buyers: {d['n_2026']}  |  "
        f"returning: {d['n_returning']}  |  "
        f"prospects: {d['n_prospects']}  |  "
        f"new: {d['n_new']}"
    )

    print("Rendering HTML…")
    html = render_html(d)

    out_dir  = os.path.join(_SCRIPT_DIR, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "retention.html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  Saved → {out_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
