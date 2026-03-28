"""
dashboard/venmo_email_backfill.py

Parse exported Venmo email messages from a local folder and emit a SharePoint-ready
CSV for one-time backfills when the Power Automate trigger missed emails.

Supported input files:
  - .eml
  - .txt (saved message body/text)

Usage:
  python dashboard/venmo_email_backfill.py --input exported-emails
  python dashboard/venmo_email_backfill.py --input exported-emails --output backfill.csv
"""

from __future__ import annotations

import argparse
import csv
import email
import html
import re
from email import policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from datetime import timezone


DEFAULT_OUTPUT = "venmo_backfill.csv"
DEFAULT_RAFFLE = "Hogs_For_the_Cause"


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        return " ".join(part.strip() for part in self.parts if part.strip())


def strip_html(value: str) -> str:
    parser = _HTMLStripper()
    parser.feed(value)
    return html.unescape(parser.get_text())


def clean_subject(subject: str) -> str:
    return re.sub(r"^(fw:|fwd:|re:)\s*", "", subject.strip(), flags=re.IGNORECASE)


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_amount(text: str) -> int | None:
    match = re.search(
        r"paid(?:\s+you|\s+\$?(?:[0-9]+(?:\.[0-9]{1,2})?)\s+to your Venmo account\.?)*\s+\$?([0-9]+(?:\.[0-9]{1,2})?)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(r"paid\s+\$?([0-9]+(?:\.[0-9]{1,2})?)\s+to your Venmo account", text, flags=re.IGNORECASE)
    if not match:
        return None
    return int(round(float(match.group(1))))


def parse_name(subject: str, body_text: str) -> str | None:
    for source in (subject, body_text):
        match = re.search(r"(.+?)\s+paid you\s+\$", source, flags=re.IGNORECASE)
        if match:
            return normalize_whitespace(match.group(1))
        match = re.search(r"(.+?)\s+paid\s+\$[0-9]+(?:\.[0-9]{1,2})?\s+to your Venmo account", source, flags=re.IGNORECASE)
        if match:
            return normalize_whitespace(match.group(1))
    return None


def parse_transaction_id(body_text: str) -> str | None:
    match = re.search(r"TRANSACTION ID\s*([A-Z0-9\-]+)", body_text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()

    fallback = re.search(r"payment ID[:\s]+([A-Z0-9\-]+)", body_text, flags=re.IGNORECASE)
    if fallback:
        return fallback.group(1).strip()
    return None


def detect_raffle(body_text: str) -> str:
    if "CRNA_Essential_Bundle" in body_text:
        return "CRNA_Essential_Bundle"
    if "Hogs for the Cause" in body_text or "Hogs_For_the_Cause" in body_text:
        return "Hogs_For_the_Cause"
    return DEFAULT_RAFFLE


def ticket_count_for_amount(amount: int | None) -> int | None:
    if amount is None:
        return None
    if amount == 25:
        return 1
    if amount == 60:
        return 3
    if amount % 100 == 0:
        return (amount // 100) * 6
    return None


def parse_email_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return value


def extract_body_from_message(message: EmailMessage) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if message.is_multipart():
        for part in message.walk():
            if part.get_content_disposition() == "attachment":
                continue
            content_type = part.get_content_type()
            try:
                content = part.get_content()
            except LookupError:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                content = payload.decode(charset, errors="replace")

            if not isinstance(content, str):
                continue
            if content_type == "text/plain":
                cleaned = normalize_whitespace(content)
                if cleaned:
                    plain_parts.append(cleaned)
            elif content_type == "text/html":
                stripped = normalize_whitespace(strip_html(content))
                if stripped:
                    html_parts.append(stripped)
    else:
        content = message.get_content()
        if isinstance(content, str):
            if message.get_content_type() == "text/html":
                stripped = normalize_whitespace(strip_html(content))
                if stripped:
                    html_parts.append(stripped)
            else:
                cleaned = normalize_whitespace(content)
                if cleaned:
                    plain_parts.append(cleaned)

    if plain_parts:
        return " ".join(plain_parts)
    if html_parts:
        return " ".join(html_parts)
    return ""


def parse_eml(path: Path) -> dict[str, str]:
    with path.open("rb") as fh:
        message = email.message_from_binary_file(fh, policy=policy.default)

    subject = str(message.get("Subject", "")).strip()
    body_text = extract_body_from_message(message)

    return {
        "source_file": str(path),
        "subject": subject,
        "clean_subject": clean_subject(subject),
        "email_from": str(message.get("From", "")).strip(),
        "submission_date": parse_email_date(message.get("Date")),
        "body_text": body_text,
    }


def parse_text_file(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8", errors="replace")
    body_text = normalize_whitespace(content)
    subject = path.stem

    return {
        "source_file": str(path),
        "subject": subject,
        "clean_subject": clean_subject(subject),
        "email_from": "",
        "submission_date": "",
        "body_text": body_text,
    }


def parse_source_file(path: Path) -> dict[str, str]:
    if path.suffix.lower() == ".eml":
        return parse_eml(path)
    if path.suffix.lower() == ".txt":
        return parse_text_file(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def build_row(parsed: dict[str, str]) -> dict[str, str]:
    subject = parsed["clean_subject"]
    body_text = parsed["body_text"]

    name = parse_name(subject, body_text)
    amount = parse_amount(subject) or parse_amount(body_text)
    transaction_id = parse_transaction_id(body_text)
    ticket_count = ticket_count_for_amount(amount)
    raffle_name = detect_raffle(body_text)

    notes: list[str] = []
    if not name:
        notes.append("name_not_found")
    if amount is None:
        notes.append("amount_not_found")
    if ticket_count is None:
        notes.append("ticket_count_unknown")
    if not transaction_id:
        notes.append("transaction_id_not_found")

    return {
        "SourceFile": parsed["source_file"],
        "ParseStatus": "ok" if not notes else "needs_review",
        "ParseNotes": ";".join(notes),
        "Title": parsed["subject"],
        "Person": name or "",
        "NumberofChances": "" if ticket_count is None else str(ticket_count),
        "PaymentReferenceID": transaction_id or "",
        "TotalPaid": "" if amount is None else str(amount),
        "SubmissionDate": parsed["submission_date"],
        "EmailAddress": parsed["email_from"],
        "RaffleName": raffle_name,
        "BodyPreview": body_text[:300],
    }


def collect_source_files(input_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".eml", ".txt"}:
            files.append(path)
    return files


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    fieldnames = [
        "SourceFile",
        "ParseStatus",
        "ParseNotes",
        "Title",
        "Person",
        "NumberofChances",
        "PaymentReferenceID",
        "TotalPaid",
        "SubmissionDate",
        "EmailAddress",
        "RaffleName",
        "BodyPreview",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a SharePoint-ready CSV from exported Venmo emails.")
    parser.add_argument("--input", required=True, help="Folder containing exported .eml or .txt files")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to output CSV file")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_path = Path(args.output)

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Input folder not found: {input_dir}")

    source_files = collect_source_files(input_dir)
    if not source_files:
        raise SystemExit(f"No .eml or .txt files found under: {input_dir}")

    rows = [build_row(parse_source_file(path)) for path in source_files]
    write_csv(rows, output_path)

    ok_count = sum(1 for row in rows if row["ParseStatus"] == "ok")
    review_count = len(rows) - ok_count
    print(f"Wrote {len(rows)} rows to {output_path}")
    print(f"  ok: {ok_count}")
    print(f"  needs_review: {review_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())