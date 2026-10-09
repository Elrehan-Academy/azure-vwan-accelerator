#!/usr/bin/env python3
import argparse
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

def az(*args):
    print("Reading Azure information...", flush=True)
    env = dict(os.environ, AZURE_EXTENSION_USE_DYNAMIC_INSTALL="no")
    result = subprocess.run(
        ["az", *args, "--output", "json", "--only-show-errors"],
        capture_output=True, text=True, timeout=180, env=env,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout or "null")

def choose(title, items, label):
    if not items:
        raise RuntimeError("No available choices: " + title)
    print("\n" + title)
    for number, item in enumerate(items, 1):
        print(f"  {number}. {label(item)}")
    while True:
        value = input("Choose a number: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(items):
            return items[int(value) - 1]
        print("Enter one of the listed numbers.")

def ask(label, default):
    return input(f"{label} [{default}]: ").strip() or default

def main():
    parser = argparse.ArgumentParser(description="Configure an existing-hub test.")
    parser.add_argument("--config", default="test-harness.local.json")
    args = parser.parse_args()
    path = Path(args.config).expanduser()
    if path.exists():
        print(f"Saved test settings already exist in the local file: {path}")
        print("This is a settings file, not an Azure resource.")
        print("Continue to choose new settings. The file changes only after")
        print("you review them and confirm saving. Azure resources are unchanged.")
        answer = input("Configure new test settings? [y/N]: ").strip().lower()
        if answer != "y":
            print("Existing configuration retained.")
            return

    subscriptions = [
        s for s in az("account", "list") if s.get("state") == "Enabled"
    ]
    sub = choose(
        "Select subscription", subscriptions,
        lambda s: f"{s['name']} — {s['id']}",
    )
    hubs = az("network", "vhub", "list", "--subscription", sub["id"])
    hub = choose(
        "Select existing hub", hubs,
        lambda h: f"{h['name']} — {h['resourceGroup']} — {h['location']}",
    )
    print("\nHub:", hub["name"], "Prefix:", hub["addressPrefix"])
    while True:
        rg = ask("New test resource group", "rg-vwan-cli-test")
        if not re.fullmatch(r"[\w().-]{1,90}", rg) or rg.endswith("."):
            print("Use a valid resource group name.")
            continue
        if rg.lower() == hub["resourceGroup"].lower():
            print("Test and core resource groups must differ.")
            continue
        if az("group", "exists", "--subscription", sub["id"], "--name", rg):
            print("That resource group exists. Choose a new name.")
            continue
        break

    size = ask("VM size (availability checked during preflight)", "Standard_B1ms")
    prefixes = []
    private = [ipaddress.ip_network(p) for p in
               ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
    hub_network = ipaddress.ip_network(hub["addressPrefix"])
    for label, default in (("Spoke A", "10.251.0.0/24"),
                           ("Spoke B", "10.252.0.0/24")):
        while True:
            try:
                network = ipaddress.ip_network(ask(label + " prefix", default))
                if network.version != 4 or network.prefixlen > 27:
                    raise ValueError("Use an IPv4 prefix /27 or larger.")
                if not any(network.subnet_of(p) for p in private):
                    raise ValueError("Use an RFC1918 private prefix.")
                if any(network.overlaps(p) for p in [hub_network, *prefixes]):
                    raise ValueError("Prefix overlaps the hub or other test spoke.")
                prefixes.append(network)
                break
            except ValueError as error:
                print(error)

    config = {
        "subscriptionId": sub["id"],
        "coreResourceGroup": hub["resourceGroup"],
        "hubName": hub["name"], "location": hub["location"],
        "testResourceGroup": rg, "vmSize": size,
        "spokeAPrefix": str(prefixes[0]), "spokeBPrefix": str(prefixes[1]),
        "adminUsername": "harnessadmin", "vmImage": "Ubuntu2204",
    }
    print("\nReview settings:\n" + json.dumps(config, indent=2))
    print("Preflight will check connected VNets, routing and diagnostics.")
    print("Also check these prefixes against other reachable networks.")
    if input("Save configuration? [y/N]: ").strip().lower() != "y":
        print("No settings saved.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(json.dumps(config, indent=2) + "\n")
    path.chmod(0o600)
    command = (
        "python3 scripts/test-harness/test-existing-hub.py --config "
        + shlex.quote(str(path)) + " --publish-report --cleanup-after"
    )
    print("\nSaved:", path)
    print("Preview:\n" + command)
    print("Run after reviewing the preview:\n" + command + " --execute")
    print("No Azure resources created or modified.")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError,
            subprocess.SubprocessError) as error:
        print("FAIL:", error, file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(1)
