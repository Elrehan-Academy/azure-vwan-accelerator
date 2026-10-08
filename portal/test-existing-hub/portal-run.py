import base64
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path("/tmp/vwan-test-workflow")
root.mkdir(parents=True, exist_ok=True)
root.chmod(0o700)

encoded = "".join(
    os.environ[f"HARNESS_BUNDLE_{index}"]
    for index in range(int(os.environ["HARNESS_BUNDLE_COUNT"]))
)
bundle = json.loads(base64.b64decode(encoded))
for relative, encoded_file in bundle["files"].items():
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise RuntimeError("Invalid bundle path.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(encoded_file))
    path.chmod(0o600)

config = json.loads(base64.b64decode(os.environ["HARNESS_CONFIG"]))
if config["testResourceGroup"].lower() == os.environ[
    "HARNESS_CONTROL_RG"
].lower():
    raise RuntimeError("Test RG must differ from automation RG.")

config_path = root / "portal-config.json"
config_path.write_text(json.dumps(config) + "\n")
config_path.chmod(0o600)

command = [
    sys.executable,
    str(root / "scripts/test-harness/test-existing-hub.py"),
    "--config", str(config_path),
    "--execute", "--use-existing-test-rg",
]
if os.environ.get("HARNESS_PUBLISH_REPORT") == "true":
    command.append("--publish-report")
if os.environ.get("HARNESS_CLEANUP_AFTER") == "true":
    command.append("--cleanup-after")

import hashlib
import shutil

token = hashlib.sha256(
    (config["subscriptionId"] + "/" + config["testResourceGroup"]).encode()
).hexdigest()[:12]
state = Path.home() / ".local/share/azure-vwan-harness" / token
output_path = Path(os.environ["AZ_SCRIPTS_OUTPUT_PATH"])
output_path.parent.mkdir(parents=True, exist_ok=True)
saved = output_path.parent / "test-evidence"
saved.mkdir(parents=True, exist_ok=True)

result = None
try:
    def az(*parts):
        response = subprocess.run(
            ["az", *parts, "--subscription", config["subscriptionId"],
             "--output", "json", "--only-show-errors"],
            text=True, capture_output=True, timeout=180,
        )
        if response.returncode:
            raise RuntimeError(response.stderr.strip())
        return json.loads(response.stdout or "null")

    group = az("group", "show", "--name", config["testResourceGroup"])
    tags = group.get("tags") or {}
    if (tags.get("purpose") != "vwan-test-harness"
            or tags.get("automationResourceGroup") !=
            os.environ["HARNESS_CONTROL_RG"]):
        raise RuntimeError("Template-created test RG tags do not match.")
    if az("resource", "list", "--resource-group", config["testResourceGroup"]):
        raise RuntimeError("Test RG is not empty; refusing to reuse it.")
    az("group", "update", "--name", config["testResourceGroup"],
       "--set", "tags.harnessId=" + token)
    result = subprocess.run(command, cwd=root)
finally:
    evidence = state / "evidence"
    if evidence.is_dir():
        shutil.copytree(evidence, saved / "runs", dirs_exist_ok=True)
    for name in ("assessment.json", "manifest.json"):
        source = state / name
        if source.is_file():
            shutil.copy2(source, saved / name)

    success = result is not None and result.returncode == 0
    output_path.write_text(json.dumps({
        "status": "Succeeded" if success else "Failed",
        "testResourceGroup": config["testResourceGroup"],
        "harnessId": token,
        "evidenceDirectory": "test-evidence",
        "cleanupRequested": "--cleanup-after" in command,
        "cleanupCompleted": success and "--cleanup-after" in command,
        "workbookPublicationRequested": "--publish-report" in command,
    }) + "\n")

if result.returncode:
    print(
        "Workflow failed. Retained evidence may be incomplete. "
        "Test resources may remain; inspect logs before cleanup.",
        file=sys.stderr,
    )
    raise SystemExit(result.returncode)

print("PASS: portal workflow completed; evidence copied to output storage.")
