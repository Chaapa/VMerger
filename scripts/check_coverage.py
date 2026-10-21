"""Assert separate line and branch floors; avoid interpreting combined coverage as either."""
import json
from pathlib import Path

data = json.loads(Path(".local/coverage.json").read_text())
total = data["totals"]
assert total["percent_statements_covered"] >= 80, "Backend line coverage is below 80%"
assert total["percent_branches_covered"] >= 75, "Backend branch coverage is below 75%"
for file in ("contracts.py", "jobs.py"):
    stats = next(v["summary"] for k, v in data["files"].items() if k.replace("\\", "/").endswith("/" + file))
    assert stats["percent_statements_covered"] >= 90, f"{file}: critical line coverage below 90%"
    assert stats["percent_branches_covered"] >= 80, f"{file}: current critical branch floor below 80%"
print("Coverage floors passed; 90% critical branch coverage remains a documented target.")
