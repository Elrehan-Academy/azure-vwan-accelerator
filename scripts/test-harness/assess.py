#!/usr/bin/env python3
import argparse
import datetime
import hashlib
import ipaddress
import json
import os
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="test-harness.local.json")
parser.add_argument("--evidence-dir")
args = parser.parse_args()
config_path = Path(args.config).resolve()
config = json.loads(config_path.read_text())
d = json.loads(config_path.with_suffix(".discovered.json").read_text())
catalog = json.loads(
    (Path(__file__).resolve().parents[2] / "modules/observability/assessment-checks.json").read_text()
)

def az(*args):
    print("Checking:", " ".join(args[:3]), flush=True)
    env = dict(os.environ)
    env["AZURE_EXTENSION_USE_DYNAMIC_INSTALL"] = "no"
    result = subprocess.run(
        ["az", *args, "--subscription", config["subscriptionId"], "--output", "json", "--only-show-errors"],
        text=True, capture_output=True, timeout=300, env=env,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout or "null")

def get(resource, version="2024-05-01"):
    return az("rest", "--method", "get", "--url",
              "https:" + "//management.azure.com" + resource
              + "?api-version=" + version)

policy = get(d["policyId"])
groups = get(d["policyId"] + "/ruleCollectionGroups")["value"]
diagnostics = get(
    d["firewallId"] + "/providers/Microsoft.Insights/diagnosticSettings",
    "2021-05-01-preview",
)["value"]

diagnostics = [
    setting.get("properties", setting)
    for setting in diagnostics
]

rules = []
for group in groups:
    for collection in group["properties"].get("ruleCollections", []):
        action = collection.get("action", {}).get("type", "")
        for rule in collection.get("rules", []):
            rules.append({
                "group": group["name"], "collection": collection["name"],
                "action": action, **rule,
            })

def unrestricted(value):
    if value == "*":
        return True
    try:
        return ipaddress.ip_network(value, strict=False).prefixlen == 0
    except ValueError:
        return False

allows = [r for r in rules if r["action"] in ("Allow", "Dnat")]
def unresolved_rule(rule):
    if (rule["action"] == "Dnat" or not rule.get("sourceAddresses")
            or rule.get("sourceIpGroups") or rule.get("destinationIpGroups")):
        return True
    if rule.get("ruleType") == "NetworkRule":
        return bool(
            rule.get("destinationFqdns")
            or not rule.get("destinationAddresses")
            or not rule.get("destinationPorts")
        )
    if rule.get("ruleType") == "ApplicationRule":
        return bool(
            not rule.get("targetFqdns") or not rule.get("protocols")
            or rule.get("fqdnTags") or rule.get("targetUrls")
            or rule.get("webCategories") or rule.get("httpHeadersToInsert")
            or any(
                p.get("protocolType") not in ("Http", "Https")
                or not isinstance(p.get("port"), int)
                for p in rule.get("protocols", [])
            )
        )
    return True

unknown = bool(policy["properties"].get("basePolicy")) or any(
    unresolved_rule(rule) for rule in allows
)
findings = []
broad_sources = []
broad_destinations = []
broad_tags = []
management = []

for rule in allows:
    name = rule["name"]
    sources = rule.get("sourceAddresses", [])
    application = rule.get("ruleType") == "ApplicationRule"
    destinations = (
        rule.get("targetFqdns", []) if application
        else rule.get("destinationAddresses", [])
    )
    ports = (
        [str(p.get("port", "")) for p in rule.get("protocols", [])]
        if application else rule.get("destinationPorts", [])
    )
    issues = []
    if any(unrestricted(v) for v in sources):
        broad_sources.append(name)
        issues.append("Unrestricted source")
    if (any(unrestricted(v) for v in destinations)
            or "*" in ports or "0-65535" in ports or "1-65535" in ports):
        broad_destinations.append(name)
        issues.append("Unrestricted destination or ports")
    if application and any("*" in value for value in destinations):
        broad_tags.append(name)
        issues.append("Wildcard FQDN scope; review necessity")
    if unresolved_rule(rule):
        issues.append("Rule scope is not fully assessed")
    if "AzureCloud" in destinations:
        broad_tags.append(name)
        issues.append("Broad AzureCloud destination; review necessity and expiry")
    for port in ports:
        try:
            limits = port.split("-")
            low, high = int(limits[0]), int(limits[-1])
            exposed = any(low <= p <= high for p in (22, 3389))
        except ValueError:
            exposed = port == "*"
        if exposed:
            management.append(name)
            issues.append("SSH/RDP allowed; review source restrictions")
            break
    findings.append({
        "rule": name, "group": rule["group"],
        "action": rule["action"], "sources": sources,
        "destinations": destinations, "ports": ports,
        "findings": issues or ["No issue detected by these limited checks"],
    })

checks = []
def add(identifier, status, observed, recommendation):
    definition = next(c for c in catalog["checks"] if c["id"] == identifier)
    checks.append({
        **definition, "status": status, "observed": observed,
        "recommendation": recommendation,
    })

logging = any(
    setting.get("workspaceId", "").lower() == d["workspaceId"].lower()
    and setting.get("logAnalyticsDestinationType") == "Dedicated"
    and any(
        log.get("enabled") and (
            log.get("categoryGroup") == "allLogs"
            or log.get("category") == "AzureFirewallNetworkRule"
        )
        for log in setting.get("logs", [])
    )
    for setting in diagnostics
)
add("N01", "Pass" if logging else "Fail",
    "Dedicated network logging configured" if logging else "Expected diagnostics absent",
    "Enable network-rule diagnostics to the selected workspace.")

workspace = az("monitor", "log-analytics", "workspace", "show",
               "--ids", d["workspaceId"])
query = (
    "AZFWNetworkRule | where TimeGenerated > ago(1h)"
    f" | where _ResourceId =~ '{d['firewallId']}'"
    " | summarize Events=count(), LatestEvent=max(TimeGenerated)"
)
try:
    logs = az("monitor", "log-analytics", "query",
              "--workspace", workspace["customerId"],
              "--analytics-query", query)
    count = int(logs[0]["Events"])
    add("N02", "Pass" if count else "Not assessed",
        f"{count} network events in the last hour",
        "Confirm traffic activity and ingestion when no events are observed.")
except (RuntimeError, KeyError, TypeError, IndexError, ValueError) as error:
    add("N02", "Not assessed", str(error), "Resolve the log-query failure.")

def rule_status(failures, reviews=None):
    if failures:
        return "Fail"
    if unknown:
        return "Not assessed"
    if reviews:
        return "Review required"
    if not allows:
        return "Not assessed"
    return "Pass"

add("N03", rule_status(broad_sources),
    {"unrestrictedSources": broad_sources, "unresolvedScope": unknown},
    "Restrict sources; assess inherited policies and referenced IP groups.")
add("N04", rule_status(broad_destinations, broad_tags),
    {"unrestrictedRules": broad_destinations, "broadServiceTags": broad_tags,
     "unresolvedScope": unknown},
    "Restrict destinations and ports; justify broad tags and temporary access.")
add("N05", rule_status([], management),
    {"managementPortRules": management, "unresolvedScope": unknown},
    "Review SSH/RDP reachability, source scope and inherited/DNAT rules.")
test_status = "Not assessed"
test_observed = "No verified test evidence folder supplied."
if args.evidence_dir:
    try:
        evidence = Path(args.evidence_dir).resolve()
        verified = json.loads((evidence / "verification.json").read_text())
        run = json.loads((evidence / "run.json").read_text())
        expected_rules = {
            "allow-private-8080", "deny-private-8081",
            "allow-web-http", "deny-web-http",
        }
        if verified["status"] != "Pass" or run["probeStatus"] != "Pass":
            raise ValueError("Evidence does not show a passing test.")
        for key in ("firewallId", "workspaceId"):
            if (verified[key].lower() != d[key].lower()
                    or run[key].lower() != d[key].lower()):
                raise ValueError("Evidence target mismatch: " + key)
        expected_token = hashlib.sha256(
            (config["subscriptionId"] + "/"
             + config["testResourceGroup"]).encode()
        ).hexdigest()[:12]
        if (verified["harnessId"] != expected_token
                or run["harnessId"] != expected_token):
            raise ValueError("Evidence harness mismatch.")
        for key in ("startedUtc", "completedUtc", "privateIps"):
            if verified[key] != run[key]:
                raise ValueError("Evidence run mismatch: " + key)
        if set(verified["verifiedRules"]) != expected_rules:
            raise ValueError("Required test rules are missing.")
        test_status = "Pass"
        test_observed = {
            "testCompletedUtc": verified["completedUtc"],
            "verifiedUtc": verified["verifiedUtc"],
            "verifiedRules": sorted(expected_rules),
            "scope": "Historical test evidence; rerun after configuration changes",
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        test_observed = "Evidence could not be validated: " + str(error)

add("N06", test_status, test_observed,
    "Rerun traffic tests after routing or policy changes; retain matching logs.")


summaries = {}
for framework in ("NIST",):
    subset = [c for c in checks if c["framework"] == framework]
    counts = {
        status: sum(c["status"] == status for c in subset)
        for status in catalog["statuses"]
    }
    assessed = counts["Pass"] + counts["Fail"]
    summaries[framework] = {
        "counts": counts,
        "assessedPassRatePercent": (
            round(100 * counts["Pass"] / assessed, 1) if assessed else None
        ),
        "coveragePercent": round(100 * assessed / len(subset), 1),
        "totalChecks": len(subset),
    }

report = {
    "generatedUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "scope": catalog["scope"],
    "firewallId": d["firewallId"], "policyId": d["policyId"],
    "workspaceId": d["workspaceId"],
    "threatIntelMode": policy["properties"].get("threatIntelMode"),
    "workspaceRetentionDays": workspace.get("retentionInDays"),
    "summary": summaries, "checks": checks, "ruleFindings": findings,
}
token = hashlib.sha256(
    (config["subscriptionId"] + "/" + config["testResourceGroup"]).encode()
).hexdigest()[:12]
folder = Path.home() / ".local/share/azure-vwan-harness" / token
folder.mkdir(parents=True, exist_ok=True)
path = folder / "assessment.json"
path.write_text(json.dumps(report, indent=2) + "\n")
path.chmod(0o600)
print(json.dumps(summaries, indent=2))
print("Assessment saved:", path)
print("No Azure resources modified.")
