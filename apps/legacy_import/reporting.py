"""Write private record-level data separately from the public sanitized summary."""

import csv
import json
from pathlib import Path


def write_reports(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "legacy-real-summary.json").write_text(
        json.dumps(report["summary"], ensure_ascii=False, indent=2) + "\n"
    )
    for area, rows in {**report["rows"], "issues": report["issues"]}.items():
        columns = sorted({key for row in rows for key in row}) or ["processo_sei", "mismatch_codes"]
        with (output / f"legacy-real-{area}-diff.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (dict, list, tuple))
                        else value
                        for key, value in row.items()
                    }
                )
