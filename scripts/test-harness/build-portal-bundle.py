#!/usr/bin/env python3
import base64
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
names = [
    "harness.py", "deploy.py", "connect.py",
    "run-tests.py", "probe.py", "prepare-server.sh",
    "verify-logs.py", "assess.py", "publish-report.py",
    "cleanup.py", "test-existing-hub.py",
]
files = {}
for name in names:
    relative = "scripts/test-harness/" + name
    path = root / relative
    content = path.read_bytes()
    if path.suffix == ".py":
        compile(content.decode(), str(path), "exec")
    files[relative] = base64.b64encode(content).decode()

relative = "modules/observability/assessment-checks.json"
catalogue = (root / relative).read_bytes()
json.loads(catalogue)
files[relative] = base64.b64encode(catalogue).decode()

output = root / "portal/test-existing-hub/scriptBundle.json"
output.write_text(json.dumps({"files": files}, indent=2) + "\n")
print(f"PASS: bundled {len(files)} code/catalogue files.")
print("Bundle:", output)
print("No local configuration, keys or evidence included.")
