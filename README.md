# Azure Virtual WAN Accelerator

<p align="left">
  <img src="https://img.shields.io/badge/Elrehan%20Academy-Mohamed%20Elrehan-0969DA?style=for-the-badge&amp;labelColor=16365D" alt="Elrehan Academy — Created and maintained by Mohamed Elrehan">
</p>

Created and maintained by **Mohamed Elrehan** for **Elrehan Academy**.

Built using [Microsoft Azure Verified Modules](https://azure.github.io/Azure-Verified-Modules/)
and adapted from Microsoft's Azure Firewall Monitor Workbook.
Workbook source revision, modifications, and license are recorded in
[the source attribution](modules/observability/SOURCE.md).

Choose a regional or multi-region network, configure its settings, and deploy
into your own Azure subscription through the Azure portal.

**Status:** Under development. The single-hub template compiles and a draft
portal form is available. Portal and live deployment validation remain
pending. Production suitability has not been established.

## Choose your blueprint

| Blueprint | Hub count | Intended use |
| --- | --- | --- |
| Regional secured vWAN | 1 | Regional connectivity and centralized traffic inspection |
| Multi-region secured vWAN | 2 by default; expandable to 4 | Connectivity and regional inspection across multiple regions |

Both blueprints will use shared Bicep modules.

## Deploy Single Hub

**Development preview:** portal behavior and live deployment validation remain pending. Deployment creates billable Azure resources.

[![Deploy Single Hub to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#blade/Microsoft_Azure_CreateUIDef/CustomDeploymentBlade/uri/https%3A%2F%2Fraw.githubusercontent.com%2FElrehan-Academy%2Fazure-vwan-accelerator%2F312f1d175f4995632a3fe88cadd5ada313f38f60%2Fportal%2Fsingle-hub%2FmainTemplate.json/uiFormDefinitionUri/https%3A%2F%2Fraw.githubusercontent.com%2FElrehan-Academy%2Fazure-vwan-accelerator%2F312f1d175f4995632a3fe88cadd5ada313f38f60%2Fportal%2Fsingle-hub%2FuiFormDefinition.json)

For the initial form check, review the inputs without selecting Create.

Multi-Hub deployment is not available yet.

## Solution components

| Component | Purpose | Planned selection |
| --- | --- | --- |
| Standard Virtual WAN | Connect hubs and their attached networks | One per environment |
| Virtual hubs | Provide regional routing and connectivity | Names, regions, and non-overlapping address prefixes |
| Azure Firewall | Inspect traffic in a secured hub | Enable per hub; Standard or Premium |
| Firewall Policy | Define firewall rules and security settings | Shared or separate policies, with explicit location |
| Routing intent | Direct private and Internet traffic through inspection | Configure per hub; validated against the selected firewall |
| Spoke connections | Attach workload networks to a selected hub | Explicit selection of existing VNets |
| Log Analytics | Collect firewall telemetry | Shared monitoring destination |
| Azure Monitor workbook | Inspect network and application firewall events | All firewalls or selected firewalls |
| VPN and ExpressRoute gateways | Connect branches and on-premises networks | Optional; disabled by default |

Disabling a hub's firewall removes Azure Firewall inspection from that hub.
Multiple hubs alone do not provide application disaster recovery.

## Deployment experience

1. Choose Single Hub or Multi-Hub.
2. Open its Deploy to Azure form.
3. Enter names, regions, address ranges, and security settings.
4. Review the configuration and estimated costs.
5. Deploy and check the deployment outputs.
6. Verify connectivity, firewall decisions, and monitoring.

The Single Hub button is available for development testing. The Multi-Hub button will be added when that blueprint is available.

## New deployments and updates

The intended deployment modes are:

- **Create:** deploy a dedicated environment after checking for name conflicts.
- **Update or expand:** explicitly select the intended existing environment
  and review the changes.

Existing resources must not be silently adopted. Resource identity and
ownership checks will be documented with the deployment implementation.
A standard Bicep deployment can update resources with matching identities;
a mode selection alone does not prevent this.

Keep existing hub identities stable when expanding the environment.
Removal will be an explicit, separately documented action.

## Costs and ownership

You own the Azure subscription, deployed resources, permissions, and costs.
Hubs, firewalls, gateways, and monitoring can incur charges while they exist.

Production deployments are retained. Automatic expiry or cleanup is not
currently provided. Optional test resources will have a separate lifecycle.

## Documentation

Read the [solution and configuration guide](docs/CONFIGURATION.md) for the architecture diagram, components, inputs, and current limitations.

The deployment guides will cover:

- **Deployment:** prerequisites, portal inputs, and expected results.
- **Configuration:** component settings and single-hub/multi-hub diagrams.
- **Operations:** monitoring, verification, updates, troubleshooting, and removal.

Documentation will distinguish available features from planned capabilities.
