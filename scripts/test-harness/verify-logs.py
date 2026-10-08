#!/usr/bin/env python3
import argparse
import datetime
import hashlib
import ipaddress
import json
import os
import subprocess
import sys
import time
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="test-harness.local.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    sub = config["subscriptionId"]
    rg = config["testResourceGroup"]
    token = hashlib.sha256((sub + "/" + rg).encode()).hexdigest()[:12]
    folder = Path.home() / ".local/share/azure-vwan-harness" / token
    if not args.execute:
        print("Preview: verify two network and two application test rules.")
        print("Add --execute to query logs; no Azure resources are modified.")
        return

    manifest = json.loads((folder / "manifest.json").read_text())
    if (manifest["harnessId"] != token
            or manifest["subscriptionId"].lower() != sub.lower()
            or manifest["testResourceGroup"].lower() != rg.lower()):
        raise RuntimeError("Manifest does not match configuration.")

    runs = sorted(
        p for p in (folder / "evidence").iterdir()
        if p.is_dir() and (p / "probes.json").exists()
    )
    if not runs:
        raise RuntimeError("No saved probe run found.")
    evidence = runs[-1]
    response = json.loads((evidence / "probes.json").read_text())
    messages = "\n".join(
        item.get("message", "") for item in response.get("value", [])
    )
    stdout = messages.split("[stdout]", 1)[-1].split("[stderr]", 1)[0]
    if "PROBES_PASS" not in stdout.splitlines():
        raise RuntimeError(
            "Saved probes did not pass; firewall logs alone cannot pass the test."
        )

    metadata = json.loads((evidence / "run.json").read_text())
    if metadata["probeStatus"] != "Pass":
        raise RuntimeError("Run metadata does not show successful probes.")
    for key in ("harnessId", "firewallId", "workspaceId", "privateIps"):
        actual = metadata[key]
        expected = manifest[key]
        if isinstance(actual, str):
            actual, expected = actual.lower(), expected.lower()
        if actual != expected:
            raise RuntimeError("Run target mismatch: " + key)

    start_time = datetime.datetime.fromisoformat(metadata["startedUtc"])
    end_time = datetime.datetime.fromisoformat(metadata["completedUtc"])
    if (start_time.utcoffset() is None or end_time.utcoffset() is None
            or end_time < start_time):
        raise RuntimeError("Invalid probe time window.")
    start = start_time.isoformat()
    end = end_time.isoformat()
    source, destination = [
        str(ipaddress.ip_address(ip)) for ip in manifest["privateIps"]
    ]
    firewall = manifest["firewallId"].replace("'", "''")
    group = "harness-" + token
    query = f"""
union
(AZFWNetworkRule
| where TimeGenerated between (datetime({start}) .. datetime({end}))
| where _ResourceId =~ '{firewall}'
| where SourceIp == '{source}' and DestinationIp == '{destination}'
| where RuleCollectionGroup == '{group}'
| where (Rule == 'allow-private-8080' and Action =~ 'Allow'
         and tostring(DestinationPort) == '8080')
     or (Rule == 'deny-private-8081' and Action =~ 'Deny'
         and tostring(DestinationPort) == '8081')
| project TimeGenerated, Rule),
(AZFWApplicationRule
| where TimeGenerated between (datetime({start}) .. datetime({end}))
| where _ResourceId =~ '{firewall}' and SourceIp == '{source}'
| where RuleCollectionGroup == '{group}'
| where (Rule == 'allow-web-http' and Action =~ 'Allow'
         and Fqdn =~ 'www.example.com')
     or (Rule == 'deny-web-http' and Action =~ 'Deny'
         and Fqdn =~ 'www.microsoft.com')
| project TimeGenerated, Rule)
| summarize Events=count(), LatestEvent=max(TimeGenerated) by Rule
"""
    env = dict(os.environ)
    env["AZURE_EXTENSION_USE_DYNAMIC_INSTALL"] = "no"

    def az(*parts):
        result = subprocess.run(
            ["az", *parts, "--subscription", sub,
             "--output", "json", "--only-show-errors"],
            text=True, capture_output=True, timeout=180, env=env,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout)
    workspace = az("monitor", "log-analytics", "workspace", "show",
                   "--ids", manifest["workspaceId"])
    expected = {
        "allow-private-8080", "deny-private-8081",
        "allow-web-http", "deny-web-http",
    }
    deadline = time.monotonic() + 600
    while True:
        print("Checking firewall log evidence...", flush=True)
        rows = az("monitor", "log-analytics", "query",
                  "--workspace", workspace["customerId"],
                  "--analytics-query", query)
        path = evidence / "firewall-log-verification.json"
        path.write_text(json.dumps(rows, indent=2) + "\n")
        path.chmod(0o600)
        found = {row.get("Rule") for row in rows}
        missing = expected - found
        print("Missing log evidence:", sorted(missing), flush=True)
        if not missing:
            verification = {
                "status": "Pass",
                "verifiedUtc": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
                "harnessId": token,
                "firewallId": manifest["firewallId"],
                "workspaceId": manifest["workspaceId"],
                "privateIps": manifest["privateIps"],
                "startedUtc": start,
                "completedUtc": end,
                "verifiedRules": sorted(expected),
            }
            result_path = evidence / "verification.json"
            result_path.write_text(json.dumps(verification, indent=2) + "\n")
            result_path.chmod(0o600)

            report = [
                "# Network test report",
                "",
                "Result: PASS — probes and matching firewall logs verified.",
                "",
                f"Firewall: `{manifest['firewallId']}`",
                f"Test window: {start} to {end}",
                "",
                "| Test rule | Result | Matching events |",
                "|---|---|---|",
            ]
            counts = {row["Rule"]: row["Events"] for row in rows}
            for rule in sorted(expected):
                report.append(f"| {rule} | Pass | {counts[rule]} |")
            report.extend([
                "",
                "Evidence: probes.json, run.json, "
                "firewall-log-verification.json and verification.json.",
                "",
                "This verifies the selected traffic tests; "
                "it is not a complete security or NIST assessment.",
                "",
            ])
            report_path = evidence / "REPORT.md"
            report_path.write_text("\n".join(report))
            report_path.chmod(0o600)
            print("Report saved:", report_path)
            print("PASS: all four expected firewall rules logged.")
            print("Evidence saved:", path)
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("Log evidence incomplete after 10 minutes.")
        time.sleep(30)

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError,
            subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
