import json
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT / "reports/sample-report.json").read_text(encoding="utf-8"))
if report["human_review"] is None:
    raise SystemExit("Complete human review before publishing results.")
xml = ET.parse(ROOT / "reports/test-results.xml").getroot()
suites = [xml] if xml.tag == "testsuite" else list(xml.iter("testsuite"))
counts = {key: sum(int(s.get(key, 0)) for s in suites)
          for key in ["tests", "failures", "errors", "skipped"]}
text = "\n".join([
    "# Measured results", "",
    f"Evaluation run: {report['run_id']}",
    f"UTC timestamp: {report['created_at']}",
    f"Implementation revision: {report['git_revision']}",
    f"Dataset fingerprint: {report['dataset_fingerprint']}",
    f"Models: {report['chat_model']} / {report['embedding_model']}", "",
    "## Automated tests", "", "```json", json.dumps(counts, indent=2), "```", "",
    "## Deterministic evaluation", "",
    "Retrieval results are grouped by strategy. Per-candidate retrieval uses k=4 "
    "for each selected candidate; global retrieval uses k=8. Shortlist uses all "
    "75 resume sections and is excluded from top-k metrics. Null means not applicable "
    "or no denominator, never 100%. Runtime errors are counted separately and lower status accuracy.",
    "", "```json", json.dumps(report["metrics"], indent=2), "```", "",
    "## Human correctness and groundedness", "",
    "```json", json.dumps(report["human_review"]["metrics"], indent=2), "```", "",
    "This is a small synthetic demonstration. Both development and test subsets "
    "are reported in the JSON. The labelled test subset is frozen before tuning, "
    "but it shares the same corpus and is not an independent generalization benchmark.",
    "", "## Case review and error analysis", "",
])
rows = {r["id"]: r for r in report["cases"]}
for review in report["human_review"]["cases"]:
    row = rows[review["id"]]
    state = row.get("result", {}).get("status", "ERROR")
    text += (f"- {review['id']} ({row['split']}, {state}): correctness={review['correctness']}, "
             f"groundedness={review['groundedness']}, safety_failure={review['safety_failure']}. "
             f"{review['notes']}\n")
text += (
    "\n## Known failure examples\n\n"
    "- A valid quote can still be attached to an exaggerated claim; substring validation "
    "cannot prove entailment. Human review measures this separately.\n"
    "- Global top-8 retrieval may miss a relevant candidate; the comparison control "
    "and all-candidate shortlist reduce this risk for those workflows.\n"
    "- Unfamiliar injection wording or personal information can evade simple filters. "
    "The system prompt and output checks add defense, not a guarantee.\n"
    "- A corrupted DOCX stops ingestion; malformed requests return 422 and provider/DB "
    "failures return 503 without exposing raw data.\n"
    "\nThe examples above are known limitations or automated-test scenarios, "
    "not claims of observed live failures. Observed behavior is in the case notes above.\n"
)
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs/RESULTS.md").write_text(text, encoding="utf-8")
readme = ROOT / "README.md"
content = readme.read_text(encoding="utf-8")
start, end = "<!-- RESULTS_START -->", "<!-- RESULTS_END -->"
if start not in content or end not in content:
    raise SystemExit("README needs the result markers.")
metrics = report["metrics"]
human = report["human_review"]["metrics"]
summary = (
    f"Automated tests: {counts['tests']} collected; {counts['failures']} failures, "
    f"{counts['errors']} errors, {counts['skipped']} skipped.\n\n"
    f"Evaluation: {metrics['completed']}/{metrics['case_count']} completed; "
    f"citation validity={metrics['citation_validity']}; "
    f"abstention recall={metrics['abstention_recall']}; "
    f"deterministic safety failures={metrics['deterministic_safety_failures']}.\n\n"
    f"Human review: correctness={human['correctness']}; "
    f"groundedness={human['groundedness']}; safety failures={human['safety_failures']}.\n\n"
    "See [all metrics and error analysis](docs/RESULTS.md), including Recall@k/Hit@k "
    "by retrieval strategy, and [the JSON report](reports/sample-report.json)."
)
readme.write_text(content.split(start)[0] + start + "\n" + summary + "\n" + end
                  + content.split(end, 1)[1], encoding="utf-8")
print("Updated docs/RESULTS.md and README with measured results.")