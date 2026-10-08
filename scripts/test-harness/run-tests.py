#!/usr/bin/env python3
import argparse
import base64
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="test-harness.local.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    sub = config["subscriptionId"]
    rg = config["testResourceGroup"]
    if rg.lower() == config["coreResourceGroup"].lower():
        raise RuntimeError("Test and core resource groups must differ.")
    token = hashlib.sha256((sub + "/" + rg).encode()).hexdigest()[:12]
    folder = Path.home() / ".local/share/azure-vwan-harness" / token
    scripts = Path(__file__).resolve().parent

    print(f"Test RG: {rg}")
    print("Prepare VM B; run private and HTTP probes from VM A.")
    if not args.execute:
        print("Preview only. Add --execute to generate test traffic.")
        return

    manifest = json.loads((folder / "manifest.json").read_text())
    if (manifest["subscriptionId"].lower() != sub.lower()
            or manifest["testResourceGroup"].lower() != rg.lower()
            or manifest["harnessId"] != token):
        raise RuntimeError("Cleanup manifest does not match configuration.")

    env = dict(os.environ)
    env["AZURE_EXTENSION_USE_DYNAMIC_INSTALL"] = "no"

    def az(*parts):
        print("Running: az " + " ".join(parts[:3]), flush=True)
        result = subprocess.run(
            ["az", *parts, "--subscription", sub,
             "--output", "json", "--only-show-errors"],
            capture_output=True, text=True, timeout=900, env=env,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout or "null")

    group = az("group", "show", "--name", rg)
    if group.get("tags", {}).get("harnessId") != token:
        raise RuntimeError("Test RG ownership tag does not match.")
    for suffix, expected in zip(("a", "b"), manifest["privateIps"]):
        nic = az("network", "nic", "show", "--resource-group", rg,
                 "--name", f"nic-harness-{suffix}")
        if nic["ipConfigurations"][0]["privateIPAddress"] != expected:
            raise RuntimeError("VM address differs from cleanup manifest.")

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    evidence = folder / "evidence" / stamp
    evidence.mkdir(parents=True, exist_ok=False)
    evidence.chmod(0o700)

    def invoke(vm, script, filename, marker):
        response = az(
            "vm", "run-command", "invoke", "--resource-group", rg,
            "--name", vm, "--command-id", "RunShellScript",
            "--scripts", script,
        )
        path = evidence / filename
        path.write_text(json.dumps(response, indent=2) + "\n")
        path.chmod(0o600)
        messages = "\n".join(
            item.get("message", "") for item in response.get("value", [])
        )
        print(messages)
        if marker not in messages.splitlines():
            raise RuntimeError(f"{marker} missing; inspect {path}")

    invoke("vm-harness-b", (scripts / "prepare-server.sh").read_text(),
           "server.json", "SERVER_READY")

    payload = base64.b64encode((scripts / "probe.py").read_bytes()).decode()
    target = manifest["privateIps"][1]
    command = (
        "set -eu\n"
        f"printf '%s' '{payload}' | base64 --decode > /tmp/vwan-probe.py\n"
        f"python3 /tmp/vwan-probe.py --target {target} --web\n"
    )
    metadata = {
        "harnessId": token,
        "firewallId": manifest["firewallId"],
        "workspaceId": manifest["workspaceId"],
        "privateIps": manifest["privateIps"],
        "startedUtc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "completedUtc": None,
        "probeStatus": "Running",
    }
    metadata_path = evidence / "run.json"

    def save_metadata():
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
        metadata_path.chmod(0o600)

    save_metadata()
    try:
        invoke("vm-harness-a", command, "probes.json", "PROBES_PASS")
        metadata["probeStatus"] = "Pass"
    except Exception:
        metadata["probeStatus"] = "Fail"
        raise
    finally:
        metadata["completedUtc"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        save_metadata()
    print("PASS: probe checks completed.")
    print("Evidence saved:", evidence)
    print("Firewall log verification remains required.")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError,
            subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
