"""
dashboard/teams_notify.py

Fetches raffle data from SharePoint (same auth + filters as generate.py) and
posts a daily summary card to Microsoft Teams via an Incoming Webhook.

Required env vars (shared with generate.py):
  AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
  SHAREPOINT_HOSTNAME, SHAREPOINT_SITE_PATH, SHAREPOINT_LIST_ID
  GOAL_AMOUNT             (Hogs goal, default 30000)
  CRNA_BUNDLE_GOAL_AMOUNT (CRNA goal, default 0 = no goal bar)

New env var:
  TEAMS_WEBHOOK_URL       (Incoming Webhook URL from the Teams channel connector)

Usage:
  python dashboard/teams_notify.py
"""

import os
import sys
from collections import defaultdict
from datetime import datetime
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
CRNA_GOAL     = int(os.environ.get("CRNA_BUNDLE_GOAL_AMOUNT", "0"))
TEAMS_URL     = os.environ["TEAMS_WEBHOOK_URL"]

_TZ          = ZoneInfo("America/Chicago")
TODAY        = datetime.now(_TZ).date()
CURRENT_YEAR = TODAY.year
TODAY_STR    = str(TODAY)          # YYYY-MM-DD

RAFFLE_CONFIGS = {
    "hogs_for_the_cause": {
        "display_name": "Hogs for the Cause",
        "goal": GOAL,
        "emoji": "🐷",
    },
    "crna_essential_bundle": {
        "display_name": "APEX CRNA Essential Bundle",
        "goal": CRNA_GOAL,
        "emoji": "💉",
    },
}

# ── Auth & Graph helpers ───────────────────────────────────────────────────────

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


def graph_get(token: str, url: str) -> dict:
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_site_id(token: str) -> str:
    data = graph_get(token, f"https://graph.microsoft.com/v1.0/sites/{SP_HOSTNAME}:{SP_SITE_PATH}")
    return data["id"]


def get_list_items(token: str, site_id: str) -> list[dict]:
    """Fetch ALL SharePoint list items (all years) with pagination."""
    url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{LIST_ID}/items"
        f"?$expand=fields&$top=999"
    )
    all_items: list[dict] = []
    while url:
        data = graph_get(token, url)
        all_items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    print(f"  Fetched {len(all_items)} total SharePoint items")
    return all_items


# ── Calculation (same filters as generate.py) ─────────────────────────────────

def calc_totals(all_items: list[dict], raffle_key: str) -> dict:
    """
    Returns:
      daily_total  – sum of TotalPaid where SubmissionDate starts with TODAY_STR
      sum_total    – sum of TotalPaid for all current-year entries (tickets > 0)
      total_tickets – ticket count for current year
      buyer_count  – unique buyer count (by Person field) for current year
    """
    daily_total   = 0.0
    sum_total     = 0.0
    total_tickets = 0
    buyers: set[str] = set()
    daily_totals: dict[str, float] = defaultdict(float)

    for item in all_items:
        fields = item.get("fields", {})

        # ── Same RaffleName filter as generate.py ──────────────────────────
        raffle = (fields.get("RaffleName") or "").strip().lower()
        if raffle != raffle_key:
            continue

        # ── Current year only ──────────────────────────────────────────────
        submission_date = fields.get("SubmissionDate") or ""
        year = submission_date[:4]
        if year != str(CURRENT_YEAR):
            continue

        # ── Skip zero-ticket entries (same as generate.py) ─────────────────
        tickets = int(fields.get("NumberofChances", 0) or 0)
        if tickets == 0:
            continue

        amount = float(fields.get("TotalPaid", 0) or 0)
        day    = submission_date[:10]
        person = str(fields.get("Person", "") or "").strip().lower()

        sum_total     += amount
        total_tickets += tickets
        if person:
            buyers.add(person)

        # Daily grouping
        if day:
            daily_totals[day] += amount
            if day == TODAY_STR:
                daily_total += amount

    return {
        "daily_total":   daily_total,
        "sum_total":     sum_total,
        "total_tickets": total_tickets,
        "buyer_count":   len(buyers),
        "daily_totals":  dict(daily_totals),
    }


# ── Teams Adaptive Card ────────────────────────────────────────────────────────

def _pct(value: float, goal: float) -> str:
    if goal <= 0:
        return "N/A"
    return f"{min(value / goal * 100, 100):.1f}%"


def _fmt(amount: float) -> str:
    return f"${amount:,.2f}"


def build_card(results: dict[str, dict]) -> dict:
    """Build a Teams Adaptive Card payload."""
    date_label = TODAY.strftime("%A, %B %-d, %Y")

    body = [
        {
            "type": "TextBlock",
            "text": f"Daily Raffle Summary — {date_label}",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        }
    ]

    for raffle_key, stats in results.items():
        cfg          = RAFFLE_CONFIGS[raffle_key]
        display_name = cfg["display_name"]
        goal         = cfg["goal"]
        emoji        = cfg["emoji"]

        daily  = stats["daily_total"]
        total  = stats["sum_total"]
        tix    = stats["total_tickets"]
        buyers = stats["buyer_count"]

        # Section header
        body.append({
            "type": "TextBlock",
            "text": f"{emoji} {display_name}",
            "weight": "Bolder",
            "size": "Medium",
            "spacing": "Large",
            "wrap": True,
        })

        facts = [
            {"title": "Today's Sales",   "value": _fmt(daily)},
            {"title": "Running Total",   "value": _fmt(total)},
            {"title": "Total Tickets",   "value": str(tix)},
            {"title": "Unique Buyers",   "value": str(buyers)},
        ]
        if goal > 0:
            facts.append({"title": "Goal Progress", "value": f"{_fmt(total)} / {_fmt(goal)} ({_pct(total, goal)})"})

        body.append({
            "type": "FactSet",
            "facts": facts,
        })

        # Progress bar (text-based) when goal is set
        if goal > 0:
            filled = int(min(total / goal * 20, 20))
            bar    = "█" * filled + "░" * (20 - filled)
            body.append({
                "type": "TextBlock",
                "text": f"`{bar}`",
                "fontType": "Monospace",
                "wrap": False,
            })

    # Workflows app (Power Automate) expects the raw Adaptive Card JSON directly,
    # not the legacy "attachments" wrapper used by the retired Incoming Webhook connector.
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": body,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"Fetching SharePoint data for {TODAY_STR} …")
    token   = get_token()
    site_id = get_site_id(token)
    items   = get_list_items(token, site_id)

    results: dict[str, dict] = {}
    for raffle_key in RAFFLE_CONFIGS:
        stats = calc_totals(items, raffle_key)
        results[raffle_key] = stats
        cfg = RAFFLE_CONFIGS[raffle_key]
        print(
            f"  {cfg['display_name']}: "
            f"today={_fmt(stats['daily_total'])}  "
            f"total={_fmt(stats['sum_total'])}  "
            f"tix={stats['total_tickets']}  "
            f"buyers={stats['buyer_count']}"
        )

    card = build_card(results)

    print("Posting to Teams …")
    resp = requests.post(TEAMS_URL, json=card, timeout=15)
    if resp.status_code in (200, 202):
        print("  Posted successfully.")
    else:
        print(f"  ERROR {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
