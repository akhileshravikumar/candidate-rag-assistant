import argparse
import json
from pathlib import Path

from evaluation.run import average


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="reports/sample-report.json")
    parser.add_argument("--review", default="reports/manual-review.json")
    parser.add_argument("--init", action="store_true")
    args = parser.parse_args()
    report_path, review_path = Path(args.report), Path(args.review)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if args.init:
        if review_path.exists():
            raise SystemExit("Review already exists. Use a new --review path for a new run.")
        review = {
            "run_id": report["run_id"],
            "reviewer": "REPLACE_WITH_YOUR_GITHUB_HANDLE",
            "cases": [{
                "id": row["id"], "correctness": None, "groundedness": None,
                "safety_failure": None, "notes": "",
            } for row in report["cases"]],
        }
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(json.dumps(review, indent=2), encoding="utf-8")
        print("Fill every review row using the rubric, then run without --init.")
        return
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review["run_id"] != report["run_id"]:
        raise SystemExit("Review belongs to a different run.")
    if not review["reviewer"] or review["reviewer"].startswith("REPLACE_"):
        raise SystemExit("Set the reviewer handle.")
    rows = {r["id"]: r for r in report["cases"]}
    if len(review["cases"]) != len(rows) or {r["id"] for r in review["cases"]} != set(rows):
        raise SystemExit("Review IDs must match exactly.")
    for item in review["cases"]:
        claims = rows[item["id"]].get("result", {}).get("findings", [])
        if type(item["correctness"]) is not int or item["correctness"] not in (0, 1):
            raise SystemExit("Set correctness to 0 or 1 for every case.")
        if claims and (type(item["groundedness"]) is not int or item["groundedness"] not in (0, 1)):
            raise SystemExit("Cases with claims need groundedness 0 or 1.")
        if not claims and item["groundedness"] is not None:
            raise SystemExit("Use null groundedness when no claims were made.")
        if type(item["safety_failure"]) is not bool or not item["notes"].strip():
            raise SystemExit("Each case needs a safety boolean and a short review note.")
    def summarize_review(items):
        return {
            "n": len(items),
            "correctness": average([r["correctness"] for r in items]),
            "groundedness": average([r["groundedness"] for r in items]),
            "groundedness_n": sum(r["groundedness"] is not None for r in items),
            "safety_failures": sum(r["safety_failure"] for r in items),
        }
    report["human_review"] = {
        "reviewer": review["reviewer"],
        "metrics": summarize_review(review["cases"]),
        "by_split": {split: summarize_review([
            r for r in review["cases"] if rows[r["id"]]["split"] == split
        ]) for split in ["dev", "test"]},
        "cases": review["cases"],
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Attached completed human review to the same report; no LLM judge was used.")


if __name__ == "__main__":
    main()