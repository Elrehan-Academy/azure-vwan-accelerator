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
    parser.add_argument("--use-existing-test-rg", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = json.loads(config_path.read_text())
    discovery_path = config_path.with_suffix(".discovered.json")
    discovered = json.loads(discovery_path.read_text())
    if time.time() - discovery_path.stat().st_mtime > 3600:
        raise RuntimeError("Discovery is over one hour old; rerun preflight.")
    for key in (
        "subscriptionId", "location", "testResourceGroup", "vmSize",
        "spokeAPrefix", "spokeBPrefix", "adminUsername",
    ):
        if config[key] != discovered[key]:
            raise RuntimeError(f"Configuration changed: {key}; rerun preflight.")
    hub_parts = discovered["hubId"].split("/")
    if (hub_parts[4].lower() != config["coreResourceGroup"].lower()
            or hub_parts[-1].lower() != config["hubName"].lower()):
        raise RuntimeError("Hub configuration changed; rerun preflight.")

    subscription = config["subscriptionId"]
    rg = config["testResourceGroup"]
    location = config["location"]
    if rg.lower() == config["coreResourceGroup"].lower():
        raise RuntimeError("Test and core resource groups must differ.")

    def az(*parts):
        print("Running: az " + " ".join(parts[:3]), flush=True)
        env = dict(os.environ)
        env["AZURE_EXTENSION_USE_DYNAMIC_INSTALL"] = "no"
        result = subprocess.run(
            ["az", *parts, "--subscription", subscription,
             "--output", "json", "--only-show-errors"],
            capture_output=True, text=True, env=env, timeout=1800,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout or "null")

    print(json.dumps({
        "testResourceGroup": rg,
        "location": location,
        "vmSize": config["vmSize"],
        "vmCount": 2,
        "publicIpCount": 0,
        "spokePrefixes": [config["spokeAPrefix"], config["spokeBPrefix"]],
    }, indent=2))
    if not args.execute:
        print("Preview only. Add --execute to create billable resources.")
        return

    if az("group", "exists", "--name", rg):
        if not args.use_existing_test_rg:
            raise RuntimeError(
                "Test resource group already exists. Refusing to overwrite it."
            )
        expected_token = hashlib.sha256(
            (subscription + "/" + rg).encode()
        ).hexdigest()[:12]
        group = az("group", "show", "--name", rg)
        tags = group.get("tags") or {}
        if (tags.get("harnessId") != expected_token
                or tags.get("purpose") != "vwan-test-harness"):
            raise RuntimeError("Existing test RG ownership tags do not match.")
        if az("resource", "list", "--resource-group", rg):
            raise RuntimeError("Existing test RG is not empty.")
        print("PASS: using an empty, owned test RG.", flush=True)

    token = hashlib.sha256(
        (subscription + "/" + rg).encode()
    ).hexdigest()[:12]
    private_dir = Path.home() / ".local/share/azure-vwan-harness" / token
    private_dir.mkdir(parents=True, exist_ok=True)
    private_dir.chmod(0o700)
    key = private_dir / "id_ed25519"
    if not key.exists():
        subprocess.run([
            "ssh-keygen", "-q", "-t", "ed25519", "-N", "",
            "-C", "vwan-harness", "-f", str(key),
        ], check=True)
    public_key = key.with_suffix(".pub").read_text().strip()

    hub = az("network", "vhub", "show",
             "--ids", discovered["hubId"])
    if (hub.get("provisioningState") != "Succeeded"
            or hub.get("routingState") != "Provisioned"):
        raise RuntimeError("Hub is not ready.")

    manifest = {
        "subscriptionId": subscription,
        "testResourceGroup": rg,
        "harnessId": token,
        "hubId": discovered["hubId"],
        "firewallId": discovered["firewallId"],
        "workspaceId": discovered["workspaceId"],
        "ruleCollectionGroupId": (
            discovered["policyId"] + "/ruleCollectionGroups/harness-" + token
        ),
        "connectionIds": [
            discovered["hubId"]
            + f"/hubVirtualNetworkConnections/harness-{token}-{suffix}"
            for suffix in ("a", "b")
        ],
        "privateIps": [
            str(ipaddress.ip_network(config[key]).network_address + 4)
            for key in ("spokeAPrefix", "spokeBPrefix")
        ],
    }
    manifest_path = private_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_path.chmod(0o600)
    print("Initial cleanup manifest saved:", manifest_path, flush=True)

    az("group", "create", "--name", rg, "--location", location,
       "--tags", "purpose=vwan-test-harness", f"harnessId={token}")

    resources = []
    for suffix, prefix in (
        ("a", config["spokeAPrefix"]),
        ("b", config["spokeBPrefix"]),
    ):
        network = ipaddress.ip_network(prefix)
        subnet = str(network)
        private_ip = str(network.network_address + 4)
        vnet = f"vnet-harness-{suffix}"
        nsg = f"nsg-harness-{suffix}"
        nic = f"nic-harness-{suffix}"
        vm = f"vm-harness-{suffix}"

        vnet_result = az(
            "network", "vnet", "create",
            "--resource-group", rg, "--name", vnet,
            "--location", location, "--address-prefixes", prefix,
            "--subnet-name", "test", "--subnet-prefixes", subnet,
        )
        az("network", "nsg", "create", "--resource-group", rg,
           "--name", nsg, "--location", location)
        az("network", "nsg", "rule", "create",
           "--resource-group", rg, "--nsg-name", nsg,
           "--name", "deny-inbound-ssh", "--priority", "100",
           "--direction", "Inbound", "--access", "Deny",
           "--protocol", "Tcp", "--source-address-prefixes", "*",
           "--source-port-ranges", "*",
           "--destination-address-prefixes", "*",
           "--destination-port-ranges", "22")
        az("network", "nic", "create",
           "--resource-group", rg, "--name", nic,
           "--location", location, "--vnet-name", vnet,
           "--subnet", "test", "--network-security-group", nsg,
           "--private-ip-address", private_ip)
        print(f"Creating {vm}; this may take several minutes.", flush=True)
        az("vm", "create", "--resource-group", rg, "--name", vm,
           "--location", location, "--nics", nic,
           "--image", config.get("vmImage", "Ubuntu2204"),
           "--size", config["vmSize"],
           "--admin-username", config["adminUsername"],
           "--authentication-type", "ssh",
           "--ssh-key-values", public_key,
           "--storage-sku", "Standard_LRS",
           "--os-disk-size-gb", "30")
        resources.append({
            "vmName": vm, "vnetName": vnet, "privateIp": private_ip,
        })

    print(json.dumps(resources, indent=2))
    print("PASS: two private VMs created.")
    print("Hub connections and firewall test rules are the next stage.")
    print("If a command failed, resources already created remain in the test RG.")
    print("SSH key retained locally at:", key)

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError,
            subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
