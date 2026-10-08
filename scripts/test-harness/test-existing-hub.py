#!/usr/bin/env python3
import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="test-harness.local.json")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--use-existing-test-rg", action="store_true")
    parser.add_argument(
        "--publish-report", action="store_true",
        help="Update the existing workbook assessment snapshot.",
    )
    parser.add_argument(
        "--cleanup-after", action="store_true",
        help="Remove test resources after successful verification.",
    )
    args = parser.parse_args()
    scripts = Path(__file__).resolve().parent
    config = Path(args.config).resolve()
    if not config.is_file():
        raise RuntimeError(f"Configuration not found: {config}")

    stages = [
        ("Preflight", "harness.py", ["preflight"]),
        ("Create test VMs", "deploy.py",
         ["--execute"] + (
             ["--use-existing-test-rg"] if args.use_existing_test_rg else []
         )),
        ("Connect spokes and add test rules", "connect.py", ["--execute"]),
        ("Generate test traffic", "run-tests.py", ["--execute"]),
        ("Verify firewall logs", "verify-logs.py", ["--execute"]),
        ("Assess test evidence", "assess.py", []),
    ]
    if args.publish_report:
        stages.append(
            ("Publish workbook assessment", "publish-report.py", ["--execute"])
        )
    if args.cleanup_after:
        stages.append(
            ("Remove test resources", "cleanup.py", ["--execute"])
        )

    commands = []
    for label, filename, options in stages:
        path = scripts / filename
        if not path.is_file():
            raise RuntimeError(f"Required script missing: {path}")
        command = [
            sys.executable, str(path), *options,
            "--config", str(config),
        ]
        commands.append((label, command))

    for number, (label, command) in enumerate(commands, 1):
        print(f"{number}. {label}", flush=True)
        if not args.execute:
            print("   " + shlex.join(command))

    if not args.execute:
        print("Preview only; no Azure calls or traffic generated.")
        print("Add --execute to create billable test resources.")
        return

    for label, command in commands:
        print(f"\nStarting: {label}", flush=True)
        if label == "Assess test evidence":
            settings = json.loads(config.read_text())
            token = hashlib.sha256(
                (settings["subscriptionId"] + "/"
                 + settings["testResourceGroup"]).encode()
            ).hexdigest()[:12]
            root = (
                Path.home() / ".local/share/azure-vwan-harness"
                / token / "evidence"
            )
            runs = sorted(
                p for p in root.iterdir()
                if p.is_dir() and (p / "probes.json").exists()
            )
            if not runs or not (runs[-1] / "verification.json").exists():
                raise RuntimeError("Latest test run has no verified evidence.")
            command = [
                *command, "--evidence-dir", str(runs[-1]),
            ]
        result = subprocess.run(command)
        if result.returncode:
            print(
                "Stopped. Existing test resources are retained "
                "for investigation.",
                file=sys.stderr,
            )
            print("Cleanup command:", shlex.join([
                sys.executable, str(scripts / "cleanup.py"),
                "--config", str(config), "--execute",
            ]), file=sys.stderr)
            raise RuntimeError(f"Stage failed: {label}")

    print("PASS: requested workflow completed.")
    if not args.cleanup_after:
        print("Test resources retained; use cleanup.py when finished.")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
