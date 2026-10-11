<p align="center">
  <img src="docs/assets/elrehan-academy-logo.png" alt="Elrehan Academy" width="400">
</p>

# Azure Virtual WAN Accelerator — Azure Firewall

**Free cloud networking education through hands-on automation.**

Created and maintained by **Mohamed Elrehan**.

Learn to deploy, test and observe Azure cloud networking using reusable
automation and guided practical exercises. The learning materials are
free; Azure resources deployed in your subscription incur charges.

Deploy Azure Virtual WAN networking with reusable Bicep modules, optional
Azure Firewall inspection and firewall observability. Choose Single Hub
for guided automated traffic testing, or Multi-Hub for core provisioning
with separate manual workload testing.

This edition uses **Microsoft Azure Firewall Standard or Premium** for
inspection. Palo Alto and other firewall vendors are not included in these
deployment options.

This project supports hands-on learning and lab validation. Production
suitability has not been established.

## Choose your deployment

| Option | Scope | Current status |
| --- | --- | --- |
| **Single Hub** | One regional hub with optional firewall inspection, gateways and monitoring | Portal deployment succeeded in lab testing |
| **Multi-Hub** | Two to four hubs with per-hub inspection and shared, separate or parent/child firewall policies | Two-hub ParentChildren portal deployment and workbook checks passed in lab testing |

Use the guided CLI workflow to validate traffic through an existing Single Hub.
Multi-Hub workloads and traffic validation use the separate manual guide.

## Deploy Single Hub

Deploy a Standard Virtual WAN and one hub into your Azure subscription.
Configure resource names, locations, the hub address prefix, firewall
inspection, optional gateways, monitoring and tags.

**Development preview:** deployment creates billable Azure resources.
Review the selected settings and applicable Azure pricing before creating.

[![Deploy Single Hub to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#blade/Microsoft_Azure_CreateUIDef/CustomDeploymentBlade/uri/https%3A%2F%2Fraw.githubusercontent.com%2FElrehan-Academy%2Fazure-vwan-accelerator%2Fedb80f7fe3005f0904e125063579d84cd95756f7%2Fportal%2Fsingle-hub%2FmainTemplate.json/uiFormDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2FElrehan-Academy%2Fazure-vwan-accelerator%2Fedb80f7fe3005f0904e125063579d84cd95756f7%2Fportal%2Fsingle-hub%2FuiFormDefinition.json)

Inspection modes are **Disabled**, **FirewallOnly**, **Private**,
**Internet** and **Both**. Disabled creates the hub without a firewall.
FirewallOnly creates a firewall without routing intent.

With firewall logging enabled, the deployment creates a Log Analytics
workspace and firewall diagnostics. Workbook deployment is optional.

VPN and ExpressRoute gateways are optional and disabled by default.
Branch and circuit connections require additional configuration.

### Test Single Hub automatically

Follow the [CLI test and cleanup guide](docs/TESTING.md).

1. Sign in with `az login --use-device-code` and install the guide's prerequisites.
2. From the repository root, run `python3 scripts/test-harness/configure.py`.
3. Choose the subscription and existing hub by number; use a separate test
   resource group, an available VM size and two unused spoke prefixes.
4. Review and save the settings. Preview the workflow:

   ```bash
   python3 scripts/test-harness/test-existing-hub.py \
     --config test-harness.local.json --publish-report --cleanup-after
   ```

5. After reviewing the preview, explicitly execute:

   ```bash
   python3 scripts/test-harness/test-existing-hub.py \
     --config test-harness.local.json --publish-report --cleanup-after --execute
   ```

The runner passes the latest verified evidence folder to the assessment.
It runs preflight, creates probes, connects spokes and test rules, generates
traffic, verifies logs, assesses evidence, publishes the workbook snapshot,
and cleans up after success. Configuration and preview do not create Azure
resources. Execution creates billable resources and changes test connections
and firewall rules.

Expected traffic results: private TCP **8080 Allow / 8081 Deny** and HTTP
**www.example.com Allow / www.microsoft.com Deny**, each with a matching
firewall log. Log ingestion may take several minutes.

The workbook assessment shows selected technical checks, findings and
coverage. It is a timestamped snapshot of the tested configuration,
not a full NIST assessment or compliance certification.

Keep the evidence and `REPORT.md` at the paths printed by the scripts.
Do not repeat the test until cleanup confirms the test connections, rule
group and resource group are removed. The core deployment remains.
For prerequisites, guided commands, expected results and cleanup,
see the [CLI test and cleanup guide](docs/TESTING.md).

The test workflow creates two private Linux VMs in a dedicated test
resource group, connects their VNets to the hub and adds temporary
firewall rules. Azure VM Run Command generates private and HTTP traffic
without requiring an SSH login.

Verification requires matching Allow/Deny firewall events; a failed
connection alone is not proof of firewall enforcement. The workflow saves
local evidence and a report. Workbook assessment publication is optional.

Successful runs can remove test resources automatically. If a stage fails,
the workflow stops and retains resources for investigation and explicit
cleanup. Testing temporarily changes hub connections and firewall rules.

### Single-Hub monitoring and assessment

The workbook includes network and application traffic tables showing
source, destination, ports, actions and rule details. FQDN and URL fields
are shown when available in the logs.

The NIST report presents selected technical checks, evidence, findings,
coverage and assessed pass rate. It is a timestamped snapshot, not a full
NIST assessment or compliance certification.

Premium firewall selection alone does not configure TLS inspection or IDPS.
The current web probes use HTTP; they do not validate HTTPS inspection.

### Single-Hub cleanup

With `--cleanup-after`, a successful test removes its owned hub connections,
temporary firewall rules and test resource group. The core deployment remains.
If a stage fails, use the explicit cleanup instructions in the
[Single-Hub test guide](docs/TESTING.md).

To remove the whole lab, retain required evidence, remove test resources,
then delete the dedicated core resource group and confirm deletion completes.

## Deploy Multi-Hub

Deploy one Standard Virtual WAN with **two to four regional hubs** in a
new dedicated resource group. Configure hub regions, private /22 prefixes,
inspection, Microsoft Azure Firewall Standard or Premium, and optional gateways.

**Development preview:** deployment creates billable Azure resources.
Review settings before selecting Create. The two-hub ParentChildren
configuration has passed portal provisioning and workbook checks.
Other combinations require validation in your environment.

[![Deploy Multi-Hub to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#blade/Microsoft_Azure_CreateUIDef/CustomDeploymentBlade/uri/https%3A%2F%2Fraw.githubusercontent.com%2FElrehan-Academy%2Fazure-vwan-accelerator%2F4ba579f8ba038c6ad5f796a912f129fe6cc0866d%2Fportal%2Fmulti-hub%2FmainTemplate.json/uiFormDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2FElrehan-Academy%2Fazure-vwan-accelerator%2F4ba579f8ba038c6ad5f796a912f129fe6cc0866d%2Fportal%2Fmulti-hub%2FuiFormDefinition.json)

Choose ParentChildren, Shared or Separate policies. ParentChildren assigns
all child policies to the parent policy region; hub regions remain independent.
VPN and ExpressRoute gateways are optional and disabled by default.

Monitoring uses one shared workspace, one workbook per secured hub and
one consolidated All Firewalls workbook. Assessment starts as Not assessed.

Follow the [portal guide](docs/MULTI-HUB-PORTAL.md) or
[CLI deployment guide](docs/multi-hub/DEPLOYMENT.md).
Create workloads and connections separately using the
[manual testing guide](docs/multi-hub/MANUAL-TESTING.md).
See the [cleanup guide](docs/multi-hub/CLEANUP.md) for removal.

### Test Multi-Hub manually

Follow the [Multi-Hub manual testing guide](docs/multi-hub/MANUAL-TESTING.md):

1. Create workload VNets and test VMs in the selected regions.
2. Connect the workload VNets to their corresponding hubs.
3. Add explicit Azure Firewall Allow/Deny rules in the appropriate policies.
4. Test within-hub, cross-hub and internet traffic for your inspection modes.
5. Match probe results with the expected firewall Allow/Deny logs.
6. Retain evidence, then remove test workloads, connections and temporary rules.

The Multi-Hub core package creates infrastructure and monitoring. Workloads,
traffic generation and evidence collection are performed separately.
The Single-Hub automated harness does not validate cross-hub traffic.

### Multi-Hub monitoring and assessment

All secured hubs send diagnostics to one shared Log Analytics workspace.
Each per-hub workbook selects its own firewall; the additional
**All Firewalls** workbook selects all deployed firewalls for centralized
traffic investigation. Network and application views show details available
in the recorded logs.

Per-hub assessment starts as **Not assessed** until a separate process supplies
assessment evidence. Manual traffic testing does not automatically publish
an assessment snapshot. The consolidated workbook displays a Not assessed
notice and does not aggregate firewall assessment scores.

### Multi-Hub cleanup

Use the [Multi-Hub cleanup guide](docs/multi-hub/CLEANUP.md).
Remove manual test workloads, connections and temporary rules first.

For portal deployments, review and delete the dedicated core resource group.
For CLI deployments, use the ownership-checked removal tool with the retained
local configuration and state. Save required evidence before deleting the
workspace, and verify deletion completes.

## Infrastructure updates

Bicep deployments can update resources with matching names and identities.
Review the target subscription, resource group and changes before deploying
into an existing environment.

Changing inspection mode to Disabled does not automatically delete an
existing firewall or its related resources. Removing a hub from an input
list does not provide an automatic resource-removal workflow.

## Costs and responsibility

You control the Azure subscription, permissions, deployed resources and
costs. Hubs, firewalls, gateways, VMs and monitoring can incur charges.

Core deployments remain until explicitly removed. Requesting deletion is
not confirmation of completion; verify resources are gone after cleanup.

Multiple hubs provide regional networking options. They do not, by
themselves, provide application disaster recovery.

## Microsoft modules and attribution

The deployment wrappers use pinned Microsoft Azure Verified Modules:

- Virtual WAN pattern: `avm/ptn/network/virtual-wan:0.2.0`
- Firewall Policy: `avm/res/network/firewall-policy:0.3.6`

See [Azure Verified Modules](https://azure.github.io/Azure-Verified-Modules/).
Published module validation does not replace validation of this project's
custom blueprints, portal forms, workbook changes or test scripts.

The workbook is adapted from Microsoft's Azure Firewall Monitor Workbook.
Source revision, modifications and license information are recorded in
[the workbook attribution](modules/observability/SOURCE.md).

## Documentation

| Deployment | Configuration and deployment | Testing | Cleanup |
| --- | --- | --- | --- |
| Single Hub | [Configuration guide](docs/CONFIGURATION.md) | [Automated CLI testing](docs/TESTING.md) | [Test and lab cleanup](docs/TESTING.md) |
| Multi-Hub | [Overview](docs/MULTI-HUB.md), [portal guide](docs/MULTI-HUB-PORTAL.md), [CLI guide](docs/multi-hub/DEPLOYMENT.md), [configuration](docs/multi-hub/CONFIGURATION.md) | [Manual workload testing](docs/multi-hub/MANUAL-TESTING.md) | [Core and workload cleanup](docs/multi-hub/CLEANUP.md) |
