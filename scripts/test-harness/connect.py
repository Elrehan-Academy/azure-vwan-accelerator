#!/usr/bin/env python3
import argparse
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
    discovered = json.loads(
        Path(args.config).with_suffix(".discovered.json").read_text()
    )
    sub = config["subscriptionId"]
    rg = config["testResourceGroup"]
    token = hashlib.sha256((sub + "/" + rg).encode()).hexdigest()[:12]
    expected_hub = (
        f"/subscriptions/{sub}/resourceGroups/{config['coreResourceGroup']}"
        f"/providers/Microsoft.Network/virtualHubs/{config['hubName']}"
    )
    if discovered["hubId"].lower() != expected_hub.lower():
        raise RuntimeError("Discovery does not match configured hub.")

    def az(*parts):
        print("Running: az " + " ".join(parts[:3]), flush=True)
        env = dict(os.environ)
        env["AZURE_EXTENSION_USE_DYNAMIC_INSTALL"] = "no"
        result = subprocess.run(
            ["az", *parts, "--subscription", sub, "--output", "json",
             "--only-show-errors"],
            text=True, capture_output=True, timeout=300, env=env,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout or "null")

    def get(resource_id):
        return az("rest", "--method", "get", "--url",
                  "https://management.azure.com" + resource_id
                  + "?api-version=2024-05-01")

    def put(resource_id, body):
        az("rest", "--method", "put", "--url",
           "https://management.azure.com" + resource_id
           + "?api-version=2024-05-01", "--body", json.dumps(body))
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            state = get(resource_id)["properties"].get("provisioningState")
            print(f"Provisioning: {state}", flush=True)
            if state == "Succeeded":
                return
            if state in ("Failed", "Canceled"):
                raise RuntimeError(f"Provisioning failed: {resource_id}")
            time.sleep(15)
        raise RuntimeError(f"Provisioning timed out: {resource_id}")

    group = az("group", "show", "--name", rg)
    if group.get("tags", {}).get("harnessId") != token:
        raise RuntimeError("Test RG ownership tag does not match.")

    ips = []
    vnets = []
    for suffix, key in (("a", "spokeAPrefix"), ("b", "spokeBPrefix")):
        nic = az("network", "nic", "show",
                 "--resource-group", rg, "--name", f"nic-harness-{suffix}")
        ip = nic["ipConfigurations"][0]["privateIPAddress"]
        expected_ip = str(ipaddress.ip_network(config[key]).network_address + 4)
        if ip != expected_ip:
            raise RuntimeError("VM address differs from configuration.")
        ips.append(ip)
        vnets.append(az("network", "vnet", "show",
                        "--resource-group", rg,
                        "--name", f"vnet-harness-{suffix}")["id"])

    def rule(name, sources, destinations, ports):
        return {
            "name": name, "ruleType": "NetworkRule",
            "ipProtocols": ["TCP"], "sourceAddresses": sources,
            "destinationAddresses": destinations, "destinationPorts": ports,
        }

    def collection(name, priority, action, rules):
        return {
            "name": name, "priority": priority,
            "ruleCollectionType": "FirewallPolicyFilterRuleCollection",
            "action": {"type": action}, "rules": rules,
        }

    rule_id = discovered["policyId"] + "/ruleCollectionGroups/harness-" + token
    body = {"properties": {
        "priority": 50000,
        "ruleCollections": [
            collection("harness-deny", 100, "Deny", [
                rule("deny-private-8081", [ips[0]], [ips[1]], ["8081"]),
            ]),
            collection("harness-allow", 200, "Allow", [
                rule("allow-private-8080", [ips[0]], [ips[1]], ["8080"]),
                rule("allow-agent-https", ips, ["AzureCloud"], ["443"]),
            ]),
        ],
    }}
    def application_rule(name, fqdn):
        return {
            "name": name,
            "ruleType": "ApplicationRule",
            "sourceAddresses": [ips[0]],
            "targetFqdns": [fqdn],
            "protocols": [{"protocolType": "Http", "port": 80}],
        }

    body["properties"]["ruleCollections"].extend([
        collection("harness-app-deny", 300, "Deny", [
            application_rule("deny-web-http", "www.microsoft.com"),
        ]),
        collection("harness-app-allow", 400, "Allow", [
            application_rule("allow-web-http", "www.example.com"),
        ]),
    ])

    connections = [
        discovered["hubId"] + f"/hubVirtualNetworkConnections/harness-{token}-{suffix}"
        for suffix in ("a", "b")
    ]
    manifest = {
        "subscriptionId": sub, "testResourceGroup": rg,
        "harnessId": token, "ruleCollectionGroupId": rule_id,
        "connectionIds": connections, "privateIps": ips,
        "hubId": discovered["hubId"], "firewallId": discovered["firewallId"],
        "workspaceId": discovered["workspaceId"],
    }
    print(json.dumps(manifest, indent=2))
    if not args.execute:
        print("Preview only; no rules or connections changed.")
        return

    groups = get(discovered["policyId"] + "/ruleCollectionGroups").get("value", [])
    matching = [
        g for g in groups if g["id"].lower() == rule_id.lower()
    ]
    reuse_rules = bool(matching)
    if reuse_rules:
        actual = get(rule_id)["properties"]
        expected = body["properties"]
        if actual.get("priority") != expected["priority"]:
            raise RuntimeError("Existing harness rule-group priority differs.")
        actual_collections = {
            c["name"]: c for c in actual.get("ruleCollections", [])
        }
        if set(actual_collections) != {
            c["name"] for c in expected["ruleCollections"]
        }:
            raise RuntimeError("Existing harness collections differ.")
        for wanted in expected["ruleCollections"]:
            found = actual_collections[wanted["name"]]
            for field in ("priority", "ruleCollectionType", "action"):
                if found.get(field) != wanted[field]:
                    raise RuntimeError("Existing harness collection differs.")
            actual_rules = {r["name"]: r for r in found.get("rules", [])}
            if set(actual_rules) != {r["name"] for r in wanted["rules"]}:
                raise RuntimeError("Existing harness rule names differ.")
            for wanted_rule in wanted["rules"]:
                found_rule = actual_rules[wanted_rule["name"]]
                for field, value in wanted_rule.items():
                    if found_rule.get(field) != value:
                        raise RuntimeError(f"Existing rule differs: {field}")
        if actual.get("provisioningState") != "Succeeded":
            raise RuntimeError("Existing rule group is not ready.")
        print("PASS: existing harness rules match; reusing them.")
    if any(
        g["properties"]["priority"] == 50000
        and g["id"].lower() != rule_id.lower() for g in groups
    ):
        raise RuntimeError("Rule-group priority 50000 is occupied.")
    existing = get(
        discovered["hubId"] + "/hubVirtualNetworkConnections"
    ).get("value", [])
    for connection in existing:
        existing_id = connection["id"].lower()
        remote = connection.get("properties", {}).get(
            "remoteVirtualNetwork", {}
        ).get("id", "").lower()
        for planned_id, planned_vnet in zip(connections, vnets):
            if existing_id == planned_id.lower():
                if remote != planned_vnet.lower():
                    raise RuntimeError("Harness connection targets another VNet.")
            elif remote == planned_vnet.lower():
                raise RuntimeError("Test VNet has a different hub connection.")

    folder = Path.home() / ".local/share/azure-vwan-harness" / token
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_path.chmod(0o600)
    print("Cleanup manifest saved:", manifest_path, flush=True)
    if not reuse_rules:
        put(rule_id, body)
    for connection_id, vnet_id in zip(connections, vnets):
        previous = next(
            (c for c in existing if c["id"].lower() == connection_id.lower()),
            None,
        )
        if previous:
            properties = get(connection_id)["properties"]
            if (properties.get("provisioningState") == "Succeeded"
                    and properties.get("enableInternetSecurity") is True):
                print("Reusing completed connection:", connection_id, flush=True)
                continue
        put(connection_id, {"properties": {
            "remoteVirtualNetwork": {"id": vnet_id},
            "enableInternetSecurity": True,

        }})
    print("PASS: firewall test rules and both hub connections provisioned.")
    print("Traffic tests and log verification are next.")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError,
            subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
