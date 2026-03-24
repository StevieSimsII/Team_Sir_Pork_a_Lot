"""
dashboard/debug_rafflenames.py

Quick diagnostic: prints ALL unique RaffleName values found in the
SharePoint list, along with item counts, so you can confirm the exact
string to filter on.

Run:
  python dashboard/debug_rafflenames.py
"""

import os
import requests
from collections import Counter

TENANT_ID     = os.environ["AZURE_TENANT_ID"]
CLIENT_ID     = os.environ["AZURE_CLIENT_ID"]
CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]
SP_HOSTNAME   = os.environ.get("SHAREPOINT_HOSTNAME", "kingsofcode.sharepoint.com")
SP_SITE_PATH  = os.environ.get("SHAREPOINT_SITE_PATH", "/sites/StevieCopilot")
LIST_ID       = os.environ["SHAREPOINT_LIST_ID"]


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
    url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{LIST_ID}/items"
        f"?$expand=fields&$top=999"
    )
    items: list[dict] = []
    while url:
        data = graph_get(token, url)
        items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return items


def main():
    print("Authenticating...")
    token   = get_token()
    site_id = get_site_id(token)
    print(f"Site ID: {site_id}")

    print("Fetching all list items...")
    items = fetch_all_items(token, site_id)
    print(f"Total items: {len(items)}\n")

    raffle_counter = Counter()
    year_by_raffle: dict[str, Counter] = {}

    for item in items:
        f      = item.get("fields", {})
        raffle = f.get("RaffleName") or "(blank/None)"
        year   = (f.get("SubmissionDate") or "")[:4] or "(no date)"
        raffle_counter[raffle] += 1
        if raffle not in year_by_raffle:
            year_by_raffle[raffle] = Counter()
        year_by_raffle[raffle][year] += 1

    print("=== Unique RaffleName values ===")
    for name, count in raffle_counter.most_common():
        print(f"  {count:>5}  repr={repr(name)}")
        for yr, ycount in sorted(year_by_raffle[name].items()):
            print(f"           {yr}: {ycount} items")

    print("\n=== Current filter string in code ===")
    print("  generate.py / retention_report.py  →  raffle.lower() == \"hogs_for_the_cause\"  (case-insensitive)")
    print("\n=== Sample first 3 raw field dicts ===")
    for item in items[:3]:
        f = item.get("fields", {})
        print({k: v for k, v in f.items() if k in ("RaffleName", "SubmissionDate", "Person", "TotalPaid")})


if __name__ == "__main__":
    main()
