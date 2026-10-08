import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="test-harness.local.json")
parser.add_argument("--execute", action="store_true")
args = parser.parse_args()

c = json.loads(Path(args.config).read_text())
d = json.loads(Path(args.config).with_suffix(".discovered.json").read_text())
token = hashlib.sha256(
    (c["subscriptionId"] + "/" + c["testResourceGroup"]).encode()
).hexdigest()[:12]
folder = Path.home() / ".local/share/azure-vwan-harness" / token
m = json.loads((folder / "manifest.json").read_text())

if c["testResourceGroup"].lower() == c["coreResourceGroup"].lower():
    raise SystemExit("STOP: test RG must differ from core RG.")
for key, expected in (
    ("subscriptionId", c["subscriptionId"]),
    ("testResourceGroup", c["testResourceGroup"]),
    ("harnessId", token),
    ("hubId", d["hubId"]),
):
    if m[key].lower() != expected.lower():
        raise SystemExit("STOP: manifest mismatch: " + key)

rule_id = d["policyId"] + "/ruleCollectionGroups/harness-" + token
connections = [
    d["hubId"] + "/hubVirtualNetworkConnections/harness-" + token + "-" + suffix
    for suffix in ("a", "b")
]
if m["ruleCollectionGroupId"].lower() != rule_id.lower():
    raise SystemExit("STOP: unexpected rule-group target.")
if sorted(x.lower() for x in m["connectionIds"]) != sorted(
    x.lower() for x in connections
):
    raise SystemExit("STOP: unexpected connection targets.")

def az(*parts):
    print("Running: az " + " ".join(parts[:3]), flush=True)
    result = subprocess.run(
        ["az", *parts, "--subscription", c["subscriptionId"],
         "--output", "json", "--only-show-errors"],
        text=True, capture_output=True, timeout=1800,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout or "null")

def url(resource_id):
    return "https:" + "//management.azure.com" + resource_id + "?api-version=2024-05-01"

def listing(parent):
    return az("rest", "--method", "get", "--url", url(parent))["value"]

connection_parent = d["hubId"] + "/hubVirtualNetworkConnections"
rule_parent = d["policyId"] + "/ruleCollectionGroups"
existing_connections = listing(connection_parent)
existing_groups = listing(rule_parent)

rg_exists = az("group", "exists", "--name", c["testResourceGroup"])
if rg_exists:
    group = az("group", "show", "--name", c["testResourceGroup"])
    if group.get("tags", {}).get("harnessId") != token:
        raise SystemExit("STOP: test RG ownership tag does not match.")

rg_prefix = (
    f"/subscriptions/{c['subscriptionId']}"
    f"/resourceGroups/{c['testResourceGroup']}/"
).lower()

for connection in existing_connections:
    if connection["id"].lower() not in [x.lower() for x in connections]:
        continue
    remote = connection["properties"]["remoteVirtualNetwork"]["id"]
    if not remote.lower().startswith(rg_prefix):
        raise SystemExit("STOP: connection targets a VNet outside the test RG.")

for group in existing_groups:
    if group["id"].lower() != rule_id.lower():
        continue
    for collection in group["properties"].get("ruleCollections", []):
        for rule in collection.get("rules", []):
            sources = rule.get("sourceAddresses", [])
            if (not sources or rule.get("sourceIpGroups")
                    or not set(sources).issubset(set(m["privateIps"]))):
                raise SystemExit("STOP: rule-group sources differ from test VMs.")

print("Cleanup targets:")
for target in connections + [rule_id, c["testResourceGroup"]]:
    print(" -", target)
if not args.execute:
    print("Preview only. Add --execute to remove these test resources.")
    raise SystemExit(0)

def remove(resource_id, parent):
    if not any(
        item["id"].lower() == resource_id.lower()
        for item in listing(parent)
    ):
        print("Already absent:", resource_id, flush=True)
        return
    az("rest", "--method", "delete", "--url", url(resource_id))
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        if not any(
            item["id"].lower() == resource_id.lower()
            for item in listing(parent)
        ):
            print("Removed:", resource_id, flush=True)
            return
        print("Waiting for deletion...", flush=True)
        time.sleep(15)
    raise RuntimeError("Deletion timed out: " + resource_id)

for connection_id in connections:
    remove(connection_id, connection_parent)
remove(rule_id, rule_parent)

if rg_exists:
    az("group", "delete", "--name", c["testResourceGroup"], "--yes")
if az("group", "exists", "--name", c["testResourceGroup"]):
    raise RuntimeError("Test RG still exists.")

print("PASS: test connections, rule group and test RG removed.")
print("Core deployment and private evidence retained.")
