# CLI test and cleanup guide

## Status and costs

Development preview: the complete combined CLI workflow still requires
live validation. Earlier lab tests verified private traffic inspection,
firewall logs, workbook publication and cleanup separately.

The test creates two billable Linux VMs and disks in a dedicated test RG,
two hub connections and temporary firewall rules. The VMs have no public
IPs. Azure VM Run Command runs tests without an SSH login.

## Prerequisites

Use Linux with Python 3, Azure CLI, Git and ssh-keygen installed.
Your Azure account needs permissions to create and remove test resources,
manage hub connections and firewall policy rules, query logs and optionally
update the workbook. The CLI workflow does not create role assignments.

The hub and firewall must be ready. Private and Internet routing intent
must target the firewall. Diagnostics must send firewall logs to one
Log Analytics workspace using Dedicated tables.

Current discovery expects the attached firewall in the hub's resource group.
Workbook publication expects one matching workbook in that resource group.

## Download and sign in

```bash
git clone https://github.com/Elrehan-Academy/azure-vwan-accelerator.git
cd azure-vwan-accelerator
az login
az account show --query '{Name:name,Id:id}' --output table
```

Use your existing checkout if already downloaded.

Install required extensions before running:

```bash
az extension add --name virtual-wan
az extension add --name azure-firewall
az extension add --name log-analytics --allow-preview true
```

## Two scripts: setup and testing

**Step 1 — Configure:** `configure.py` guides you through subscription,
hub and test settings, then saves a local JSON file. It only reads Azure
information. It does not create VMs, connect networks or generate traffic.

**Step 2 — Test:** `test-existing-hub.py` reads the saved settings.
Without `--execute`, it only displays the planned stages.

With `--execute`, the test workflow:
1. Checks the hub, firewall, routing and diagnostics.
2. Creates two private Linux VMs in a separate test resource group.
3. Connects their VNets to the vWAN hub using hub connections.
4. Adds temporary firewall rules and generates private and web traffic.
5. Verifies matching firewall logs and creates a technical assessment.
6. Updates the workbook when `--publish-report` is selected.
7. Removes test connections, temporary rules and the test RG after success
   when `--cleanup-after` is selected.

These are vWAN hub connections, rather than direct VNet-to-VNet peerings.
Azure Firewall generates the logs as it processes the test traffic.

If a stage fails, execution stops and test resources remain for investigation.
Use the explicit cleanup instructions below. The core deployment remains
after test cleanup.

## Collect and configure settings

Run the guided setup from the repository folder:

```bash
python3 scripts/test-harness/configure.py
```

1. Choose your subscription by number.
2. Choose an existing hub by number.
3. Enter a new test resource group name, separate from the core RG.
4. Enter a VM size, or press Enter for the example default.
5. Enter two unused private spoke prefixes.
6. Review the settings and confirm saving.

The subscription ID, hub name, core RG and region are filled automatically.
No JSON editing or placeholder replacement is required.

An existing local settings file changes only after final save confirmation.
This does not replace or delete Azure resources.
If no hub is available, setup stops without saving. Deploy Single Hub first.

Setup checks prefixes against the hub and each other. Live preflight also
checks directly connected VNets. Check other reachable networks yourself.
VM availability, quota and live capacity still require validation.

Setup only reads Azure information and saves local settings.
It prints preview and execution commands. Resource creation requires
the separate test command with --execute.

## Preview the workflow

```bash
python3 scripts/test-harness/test-existing-hub.py \
  --config test-harness.local.json \
  --publish-report \
  --cleanup-after
```

Expected: eight planned stages and `Preview only`.
This preview makes no Azure calls. It does not validate Azure readiness.

## Run the test

```bash
python3 scripts/test-harness/test-existing-hub.py \
  --config test-harness.local.json \
  --publish-report \
  --cleanup-after \
  --execute
```

The workflow checks prerequisites, creates two private VMs, connects their
spokes, adds temporary rules, generates traffic, verifies logs, creates a
NIST technical assessment, publishes it and cleans up test resources.

Omit `--publish-report` to keep the assessment local.
Omit `--cleanup-after` to retain test resources.

Allow tens of minutes and follow printed progress. Keep the terminal
running. A failed stage stops execution and retains resources; automatic
cleanup runs only after the preceding stages succeed.

## Expected results and success criteria

| Test | Expected probe result | Required firewall log |
| --- | --- | --- |
| VM A to VM B, TCP 8080 | Expected HTTP response | Matching network Allow |
| VM A to VM B, TCP 8081 | Connection blocked | Matching network Deny |
| HTTP www.example.com | Allowed response | Matching application Allow |
| HTTP www.microsoft.com | Blocked | Matching application Deny |

Probe results must match the test rule group, source, destination or FQDN,
and the saved run's time window. A timeout alone is not proof of enforcement.

Web tests use HTTP port 80. They do not validate HTTPS inspection or full
HTTPS URL visibility.

The scripts print evidence locations under:
`~/.local/share/azure-vwan-harness/<harness-id>/evidence/<run-timestamp>/`.
Retain REPORT.md and associated evidence.

When publication is selected, the workbook assessment snapshot must update.
The report maps selected technical checks to NIST outcomes; it is not
a full NIST assessment or compliance certification.

A complete pass requires all stages to succeed and cleanup to confirm:
- Both test hub connections are removed.
- The temporary firewall rule collection group is removed.
- The test RG no longer exists.
- The core hub, firewall, policy, workspace and workbook remain.

## Clean up test resources after a failure or retained run

Preview the owned cleanup targets:

```bash
python3 scripts/test-harness/cleanup.py --config test-harness.local.json
```

Remove them:

```bash
python3 scripts/test-harness/cleanup.py \
  --config test-harness.local.json \
  --execute
```

This removes the test hub connections, temporary rule group and test RG.
It retains core resources and local evidence.

Keep the discovery file and cleanup manifest until removal is verified.
If ownership checks fail or files are missing, inspect resources before
taking manual action. Deleting only the VMs leaves connections and rules.

Verify the test RG is absent:

```bash
az group exists \
  --subscription "YOUR_SUBSCRIPTION_ID" \
  --name "YOUR_TEST_RESOURCE_GROUP"
```

Expected: `false`.

## Delete the entire core lab

First clean up test resources and save any evidence you need.
Only delete a core RG dedicated to this lab: every resource in it is removed.

Inspect the resources:

```bash
az resource list \
  --subscription "YOUR_SUBSCRIPTION_ID" \
  --resource-group "YOUR_CORE_RESOURCE_GROUP" \
  --output table
```

Delete the core RG, including its vWAN, hub, firewall, policy, workspace
and workbook:

```bash
az group delete \
  --subscription "YOUR_SUBSCRIPTION_ID" \
  --name "YOUR_CORE_RESOURCE_GROUP" \
  --yes \
  --no-wait
```

Check completion later:

```bash
az group exists \
  --subscription "YOUR_SUBSCRIPTION_ID" \
  --name "YOUR_CORE_RESOURCE_GROUP"
```

Expected: `false`. An accepted deletion request is not completed deletion.
Azure continues processing after the terminal closes. Costs can continue
until resource removal completes.

Resources outside the core and test RGs require separate cleanup.

## Users of the retired portal test preview

The portal test automation has been retired in favour of the CLI workflow.
Removing its repository files does not remove previously deployed resources.

Earlier deployments may leave an automation RG containing a deployment
script, container, storage account and managed identity, plus a separately
generated test RG and role assignments outside those groups.

Inspect and remove those dedicated resources separately. Do not assume
the CLI cleanup removes the old automation or its role assignments.
