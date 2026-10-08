#!/usr/bin/env python3
import argparse
import ipaddress
import json
import os
import subprocess
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["preflight"])
    parser.add_argument("--config", default="test-harness.local.json")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())

    required = [
        "subscriptionId", "coreResourceGroup", "hubName", "location",
        "testResourceGroup", "vmSize", "spokeAPrefix", "spokeBPrefix",
        "adminUsername",
    ]
    for key in required:
        if not config.get(key):
            raise RuntimeError(f"Missing configuration: {key}")
    if config["testResourceGroup"].lower() == config["coreResourceGroup"].lower():
        raise RuntimeError("Test resource group must differ from the core group.")

    def az(*parts):
        print("Running: az " + " ".join(parts[:3]), flush=True)
        env = dict(os.environ)
        env["AZURE_EXTENSION_USE_DYNAMIC_INSTALL"] = "no"
        result = subprocess.run(
            ["az", *parts, "--subscription", config["subscriptionId"],
             "--output", "json", "--only-show-errors"],
            text=True, capture_output=True, timeout=180, env=env,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout or "null")

    rg = config["coreResourceGroup"]
    hub = az("network", "vhub", "show",
             "--resource-group", rg, "--name", config["hubName"])
    if hub.get("provisioningState") != "Succeeded":
        raise RuntimeError("Hub deployment has not succeeded.")
    if hub.get("routingState") != "Provisioned":
        raise RuntimeError("Hub routing is not provisioned.")
    if hub["location"].lower() != config["location"].lower():
        raise RuntimeError("Configured location differs from the hub location.")

    networks = [
        ipaddress.ip_network(hub["addressPrefix"]),
        ipaddress.ip_network(config["spokeAPrefix"]),
        ipaddress.ip_network(config["spokeBPrefix"]),
    ]
    for network in networks[1:]:
        if network.version != 4 or not network.subnet_of(
            ipaddress.ip_network("10.0.0.0/8")
        ) and not network.subnet_of(
            ipaddress.ip_network("172.16.0.0/12")
        ) and not network.subnet_of(
            ipaddress.ip_network("192.168.0.0/16")
        ):
            raise RuntimeError("Test prefixes must use RFC1918 IPv4 addresses.")
        if network.prefixlen > 27:
            raise RuntimeError("Test prefixes must be /27 or larger.")
    for index, left in enumerate(networks):
        for right in networks[index + 1:]:
            if left.overlaps(right):
                raise RuntimeError(f"Overlapping prefixes: {left} and {right}")

    connections = az("network", "vhub", "connection", "list",
                     "--resource-group", rg, "--vhub-name", config["hubName"])
    for connection in connections:
        remote = connection.get("remoteVirtualNetwork", {}).get("id")
        if not remote:
            continue
        vnet = az("network", "vnet", "show", "--ids", remote)
        for prefix in vnet["addressSpace"]["addressPrefixes"]:
            existing = ipaddress.ip_network(prefix)
            for planned in networks[1:]:
                if existing.overlaps(planned):
                    raise RuntimeError(
                        f"Test prefix {planned} overlaps connected VNet {prefix}"
                    )

    firewalls = az("network", "firewall", "list", "--resource-group", rg)
    matches = [
        firewall for firewall in firewalls
        if firewall.get("virtualHub", {}).get("id", "").lower()
        == hub["id"].lower()
    ]
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one Azure Firewall attached to the hub.")
    firewall = matches[0]
    if firewall.get("provisioningState") != "Succeeded":
        raise RuntimeError("Firewall deployment has not succeeded.")
    policy_id = firewall.get("firewallPolicy", {}).get("id")
    if not policy_id:
        raise RuntimeError("Firewall has no associated policy.")

    if (config.get("expectedPolicyId")
            and config["expectedPolicyId"].lower() != policy_id.lower()):
        raise RuntimeError("Selected policy is not attached to this firewall.")

    intents = az(
        "rest", "--method", "get",
        "--url", "https://management.azure.com" + hub["id"]
        + "/routingIntent?api-version=2024-05-01",
    )
    policies = [
        policy
        for intent in intents.get("value", [])
        for policy in intent.get("properties", {}).get("routingPolicies", [])
    ]
    for traffic in ("PrivateTraffic", "Internet"):
        if not any(
            traffic in policy.get("destinations", [])
            and policy.get("nextHop", "").lower() == firewall["id"].lower()
            for policy in policies
        ):
            raise RuntimeError(f"{traffic} routing intent must target this firewall.")

    diagnostics = az("monitor", "diagnostic-settings", "list",
                     "--resource", firewall["id"])
    settings = diagnostics.get("value", []) if isinstance(diagnostics, dict) else diagnostics
    workspace_ids = {
        setting["workspaceId"]
        for setting in settings
        if setting.get("workspaceId")
        and any(log.get("enabled") for log in setting.get("logs", []))
        and setting.get("logAnalyticsDestinationType") == "Dedicated"
    }
    if len(workspace_ids) != 1:
        raise RuntimeError(
            "Expected firewall logs sent to one workspace using Dedicated tables."
        )

    if (config.get("expectedWorkspaceId")
            and config["expectedWorkspaceId"].lower()
            != next(iter(workspace_ids)).lower()):
        raise RuntimeError("Selected workspace does not receive firewall logs.")

    print("Checking regional VM SKU restrictions...", flush=True)
    skus = az("vm", "list-skus", "--location", config["location"],
              "--resource-type", "virtualMachines",
              "--size", config["vmSize"], "--all")
    eligible = [
        sku for sku in skus
        if sku["name"] == config["vmSize"]
        and not any(
            restriction.get("type") == "Location"
            for restriction in sku.get("restrictions", [])
        )
    ]
    if not eligible:
        raise RuntimeError("VM size is unavailable or region-restricted.")
    print("PASS: hub, firewall, routing intent and diagnostics.")
    print("PASS: test prefixes do not overlap the hub or connected VNets.")
    print("PASS: VM SKU has no listed location restriction.")
    print("Quota and live capacity will still be checked during deployment.")
    discovered = {
        "hubId": hub["id"],
        "firewallId": firewall["id"],
        "policyId": policy_id,
        "workspaceId": next(iter(workspace_ids)),
        "testResourceGroup": config["testResourceGroup"],
        "vmSize": config["vmSize"],
        "subscriptionId": config["subscriptionId"],
        "location": config["location"],
        "spokeAPrefix": config["spokeAPrefix"],
        "spokeBPrefix": config["spokeBPrefix"],
        "adminUsername": config["adminUsername"],
    }
    state = Path(args.config).with_suffix(".discovered.json")
    git = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True, capture_output=True,
    ) if __import__("shutil").which("git") else None
    if git is not None and git.returncode == 0:
        root = Path(git.stdout.strip()).resolve()
        try:
            relative = state.resolve().relative_to(root)
        except ValueError:
            relative = None
        if relative is not None:
            exclude_result = subprocess.run(
                ["git", "rev-parse", "--git-path", "info/exclude"],
                text=True, capture_output=True,
            )
            if exclude_result.returncode:
                raise RuntimeError("Cannot locate Git exclusion file.")
            exclude = Path(exclude_result.stdout.strip())
            entry = "/" + relative.as_posix()
            existing = exclude.read_text() if exclude.exists() else ""
            if entry not in existing.splitlines():
                with exclude.open("a") as stream:
                    stream.write("\n" + entry + "\n")
    state.write_text(json.dumps(discovered, indent=2) + "\n")
    state.chmod(0o600)
    print(json.dumps(discovered, indent=2))
    print("Discovery saved to:", state)
    print("No Azure resources created or modified.")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
