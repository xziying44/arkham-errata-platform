"""汇总 mapping_image_diff_preview.json 中的可疑差异。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="/Users/xziying/project/arkham/errata-platform/data/mapping_image_diff_preview.json")
    parser.add_argument("--output", default="/Users/xziying/project/arkham/errata-platform/data/mapping_image_diff_suspicious.csv")
    parser.add_argument("--threshold", type=float, default=65.0)
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    ok_items = [item for item in data if item.get("diff_status") == "ok"]
    suspicious = [item for item in ok_items if float(item.get("rmse", 0)) > args.threshold]
    suspicious.sort(key=lambda item: float(item.get("rmse", 0)), reverse=True)

    skipped = {}
    for item in data:
        if item.get("diff_status") != "ok":
            skipped[item.get("diff_status", "unknown")] = skipped.get(item.get("diff_status", "unknown"), 0) + 1

    fields = [
        "arkhamdb_id", "local_face", "tts_lookup_id", "tts_side", "rmse", "source_reason",
        "relative_path", "tts_path", "zh_tts_path", "local_image", "zh_image",
    ]
    output = Path(args.output)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for item in suspicious:
            writer.writerow({field: item.get(field, "") for field in fields})

    print(json.dumps({
        "total": len(data),
        "ok": len(ok_items),
        "threshold": args.threshold,
        "suspicious": len(suspicious),
        "skipped": skipped,
        "output": str(output),
        "top20": [
            {"arkhamdb_id": item.get("arkhamdb_id"), "local_face": item.get("local_face"), "rmse": item.get("rmse"), "local_image": item.get("local_image"), "zh_image": item.get("zh_image")}
            for item in suspicious[:20]
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
