# Azure Virtual WAN Accelerator

Created and maintained by **Mohamed Elrehan** for **Elrehan Academy**.

Deploy Azure Virtual WAN networking with reusable Bicep modules, optional
Azure Firewall inspection and firewall observability. Use the CLI test
workflow to create temporary workloads, generate traffic and verify
firewall decisions against recorded logs.

This project supports hands-on learning and lab validation. Production
suitability has not been established.

## Choose your deployment

| Option | Scope | Current status |
| --- | --- | --- |
| **Single Hub** | One regional hub with optional firewall inspection, gateways and monitoring | Portal deployment succeeded in lab testing |
| **Multi-Hub** | Two to four hubs with per-hub inspection and shared, separate or parent/child firewall policies | Bicep draft; compilation and offline configuration checks passed |

Single-Hub stages were exercised in a West Europe lab on 9 October 2026:
private and HTTP Allow/Deny probes, all four matching firewall rule logs,
and evidence-based workbook assessment publication passed after the fixes
included here. Cleanup confirmation and a fresh combined rerun are pending.
Multi-Hub deployment and cross-hub traffic validation are pending.

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

## Prepare Multi-Hub

The draft blueprint creates one Standard Virtual WAN with **two to four
hubs**. Each hub has its own region, address prefix, inspection mode and
optional tags. Enabled firewalls use a common selected tier.

Choose one policy design:

| Mode | Policy design |
| --- | --- |
| **Shared** | One policy attached to all enabled firewalls |
| **Separate** | An independent policy for each enabled firewall |
| **ParentChildren** | A common parent with a child policy for each enabled firewall |

The monitoring draft uses one shared workspace and a workbook for each
enabled firewall. All resources are deployed into one resource group.

Read the [Multi-Hub draft guide](docs/MULTI-HUB.md) for configuration
examples, validation commands and current limitations.

**No Multi-Hub portal button is published yet.** The existing CLI testing
and report-publication workflow is not yet validated for Multi-Hub.

## Test an existing Single Hub

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
firewall log. HTTP 403 or 470 is only a denial candidate until the matching
application Deny log is verified. Log ingestion may take several minutes.

The lab assessment had **5 Pass, 0 Fail, 0 Not assessed, 1 Review required**
(83.3% coverage). The remaining review concerned the temporary
`allow-agent-https` rule to `AzureCloud:443`; results vary with your policy.
The published assessment is a snapshot of the tested configuration before
cleanup, not a full NIST assessment.

Keep the evidence and `REPORT.md` at the paths printed by the scripts.
Do not repeat the test until cleanup confirms the test connections, rule
group and resource group are removed. The core deployment remains.
For individual stage commands, evidence selection and troubleshooting,
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

## Observe and assess

The workbook includes network and application traffic tables showing
source, destination, ports, actions and rule details. FQDN and URL fields
are shown when available in the logs.

The NIST report presents selected technical checks, evidence, findings,
coverage and assessed pass rate. It is a timestamped snapshot, not a full
NIST assessment or compliance certification.

Premium firewall selection alone does not configure TLS inspection or IDPS.
The current web probes use HTTP; they do not validate HTTPS inspection.

## Update and remove resources

Bicep deployments can update resources with matching names and identities.
Review the target subscription, resource group and changes before deploying
into an existing environment.

Changing inspection mode to Disabled does not automatically delete an
existing firewall or its related resources. Removing a hub from an input
list does not provide an automatic resource-removal workflow.

The [cleanup guide](docs/TESTING.md) distinguishes:

- **Test cleanup:** remove owned test connections, temporary firewall rules
  and the dedicated test resource group.
- **Full lab cleanup:** after test cleanup and evidence retention, explicitly
  delete the dedicated core resource group.

Full resource-group deletion removes every resource in that group.
Resources in other groups require separate cleanup.

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

| Guide | Contents |
| --- | --- |
| [Configuration](docs/CONFIGURATION.md) | Architecture, components and configuration guidance |
| [CLI testing and cleanup](docs/TESTING.md) | Guided setup, commands, success criteria and removal |
| [Multi-Hub draft](docs/MULTI-HUB.md) | Policy modes, examples, offline checks and remaining validation |
