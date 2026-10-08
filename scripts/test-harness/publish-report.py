import argparse
import hashlib
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="test-harness.local.json")
parser.add_argument("--execute", action="store_true")
args = parser.parse_args()
if not args.execute:
    print("Preview: update only the existing workbook assessment snapshot.")
    print("Add --execute to publish; no Azure calls performed.")
    raise SystemExit(0)

config_path = Path(args.config).resolve()
config = json.loads(config_path.read_text())
d = json.loads(config_path.with_suffix(".discovered.json").read_text())
token = hashlib.sha256(
    (config["subscriptionId"] + "/" + config["testResourceGroup"]).encode()
).hexdigest()[:12]
folder = Path.home() / ".local/share/azure-vwan-harness" / token
report = json.loads((folder / "assessment.json").read_text())

for key in ("firewallId", "policyId", "workspaceId"):
    if report[key].lower() != d[key].lower():
        raise SystemExit("STOP: assessment targets differ from discovery.")

def az(*args):
    result = subprocess.run(
        ["az", *args, "--output", "json", "--only-show-errors"],
        text=True, capture_output=True, timeout=300,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout or "null")

resources = az(
    "resource", "list",
    "--subscription", config["subscriptionId"],
    "--resource-group", config["coreResourceGroup"],
    "--resource-type", "Microsoft.Insights/workbooks",
)
matches = []
for resource in resources:
    workbook = az(
        "resource", "show", "--ids", resource["id"],
        "--api-version", "2022-04-01",
    )
    source = workbook.get("properties", {}).get("sourceId", "")
    if source.lower() == d["workspaceId"].lower():
        matches.append(workbook)

if len(matches) != 1:
    raise SystemExit("STOP: expected one workbook for this workspace.")

workbook = matches[0]
data = json.loads(workbook["properties"]["serializedData"])
snapshot_parameters = [
    p for item in data["items"] if item.get("type") == 9
    for p in item.get("content", {}).get("parameters", [])
    if p.get("name") == "AssessmentSnapshot"
]
if len(snapshot_parameters) != 1:
    raise SystemExit("STOP: expected exactly one snapshot parameter.")
snapshot_parameters[0]["value"] = json.dumps(report)

serialized = json.dumps(data, ensure_ascii=False).replace(
    "__WORKSPACE_RESOURCE_ID__", d["workspaceId"]
).replace("__FIREWALL_RESOURCE_ID__", d["firewallId"])

from datetime import datetime, timezone
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = folder / f"workbook-backup-{stamp}.json"
backup.write_text(json.dumps(workbook, indent=2) + "\n")
backup.chmod(0o600)

properties = workbook["properties"]
payload = {
    "location": workbook["location"],
    "kind": workbook.get("kind", "shared"),
    "tags": workbook.get("tags") or {},
    "properties": {
        "displayName": properties["displayName"],
        "serializedData": serialized,
        "version": properties.get("version", "1.0"),
        "sourceId": properties["sourceId"],
        "category": properties.get("category", "workbook"),
    },
}
body = folder / "workbook-report-update.json"
body.write_text(json.dumps(payload) + "\n")
body.chmod(0o600)

print("Backup saved:", backup, flush=True)
print("Publishing snapshot:", report["generatedUtc"], flush=True)
updated = az(
    "rest", "--method", "put",
    "--url", "https:" + "//management.azure.com" + workbook["id"]
    + "?api-version=2022-04-01",
    "--body", "@" + str(body),
)
print("PASS: workbook report published.")
print("Workbook:", updated.get("id", workbook["id"]))
