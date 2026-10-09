#!/usr/bin/env python3
import argparse
import ipaddress
import json
import sys
from pathlib import Path

def require(condition, message):
    if not condition:
        raise ValueError(message)

def name(value, label):
    require(isinstance(value, str) and bool(value.strip()),
            label + " must be a non-empty string.")
    return value.casefold()

def validate(path):
    data = json.loads(path.read_text())
    parameters = data["parameters"]
    require(all(isinstance(v, dict) and "value" in v
                for v in parameters.values()),
            "Use concrete parameter values; references are not supported.")
    p = {k: v["value"] for k, v in parameters.items()}
    name(p["virtualWanName"], "virtualWanName")
    hubs = p["hubs"]
    require(isinstance(hubs, list) and 2 <= len(hubs) <= 4,
            "Provide two to four hubs.")
    mode = p.get("policyMode", "ParentChildren")
    require(mode in ("Shared", "Separate", "ParentChildren"),
            "Invalid policyMode.")
    require(p.get("firewallTier", "Standard") in ("Standard", "Premium"),
            "Invalid firewallTier.")
    require(isinstance(p.get("tags", {}), dict), "Common tags must be an object.")
    if mode == "Separate":
        require(not p.get("commonRuleCollectionGroups", []),
                "Separate mode cannot use common rules.")

    allowed = {
        "hubName", "hubLocation", "hubAddressPrefix", "inspectionMode",
        "firewallName", "firewallPolicyName", "firewallPolicyLocation",
        "firewallPublicIpCount", "firewallZones", "ruleCollectionGroups",
        "tags", "s2sVpnParameters", "expressRouteParameters"
    }
    seen_hubs, seen_firewalls, seen_policies = set(), set(), set()
    networks = []
    secured = 0
    common = name(p.get("commonPolicyName", p["virtualWanName"] + "-policy"),
                  "commonPolicyName")
    for index, hub in enumerate(hubs, 1):
        label = f"Hub {index}"
        require(isinstance(hub, dict), label + " must be an object.")
        require(not set(hub) - allowed,
                label + " has unknown fields: " + str(set(hub) - allowed))
        hub_name = name(hub["hubName"], label + " name")
        require(hub_name not in seen_hubs, "Duplicate hub name.")
        seen_hubs.add(hub_name)
        name(hub["hubLocation"], label + " location")
        network = ipaddress.ip_network(hub["hubAddressPrefix"])
        require(network.version == 4 and network.prefixlen <= 24,
                label + " prefix must be IPv4 /24 or larger.")
        require(not any(network.overlaps(n) for n in networks),
                label + " prefix overlaps another hub.")
        networks.append(network)
        require(isinstance(hub.get("tags") or {}, dict),
                label + " tags must be an object.")
        inspection = hub.get("inspectionMode") or "Both"
        require(inspection in ("Disabled", "FirewallOnly", "Private", "Internet", "Both"),
                label + " has an invalid inspectionMode.")
        if inspection == "Disabled":
            continue
        secured += 1
        firewall = name(hub.get("firewallName") or hub["hubName"] + "-fw",
                        label + " firewallName")
        require(firewall not in seen_firewalls, "Duplicate firewall name.")
        seen_firewalls.add(firewall)
        count = hub.get("firewallPublicIpCount")
        count = 1 if count is None else count
        require(type(count) is int and 1 <= count <= 80,
                label + " public IP count must be 1–80.")
        zones = hub.get("firewallZones") or []
        require(isinstance(zones, list)
                and all(type(z) is int and z in (1, 2, 3) for z in zones)
                and len(zones) == len(set(zones)),
                label + " zones must be unique numbers from 1, 2, 3.")
        rules = hub.get("ruleCollectionGroups") or []
        require(isinstance(rules, list), label + " rules must be an array.")
        if mode == "Shared":
            require(not rules, "Shared mode cannot use per-hub rules.")
        else:
            policy = name(hub.get("firewallPolicyName") or hub["hubName"] + "-policy",
                          label + " policy name")
            require(policy not in seen_policies, "Duplicate per-hub policy name.")
            require(mode != "ParentChildren" or policy != common,
                    "A child policy name conflicts with the parent.")
            seen_policies.add(policy)
    require(secured > 0 or not p.get("commonRuleCollectionGroups", []),
            "Common rules were supplied but no firewall is enabled.")
    return f"{len(hubs)} hubs; {secured} firewalls; {mode} policy mode"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.files:
        print("PASS:", path, "—", validate(path))
    print("Offline checks only; no Azure calls.")

if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        print("FAIL:", error, file=sys.stderr)
        sys.exit(1)
