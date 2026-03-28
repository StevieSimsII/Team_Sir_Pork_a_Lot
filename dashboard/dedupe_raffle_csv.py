import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = REPO_ROOT / "data" / "reference" / "hogs-for-the-cause-2025-raffle.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "generated" / "hogs-for-the-cause-2025-raffle-dedup.csv"


def main() -> None:
    seen = set()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with INPUT_PATH.open(newline="", encoding="utf-8-sig") as source, OUTPUT_PATH.open(
        "w", newline="", encoding="utf-8"
    ) as output:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(output, reader.fieldnames)
        writer.writeheader()

        for row in reader:
            key = row["Email Address"].strip().lower() or row["Phone Number"].strip()
            if key in seen:
                continue
            seen.add(key)
            writer.writerow(row)


if __name__ == "__main__":
    main()