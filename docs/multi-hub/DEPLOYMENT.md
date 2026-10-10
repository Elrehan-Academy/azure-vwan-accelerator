# Elrehan Academy — Multi-Hub deployment

## Prerequisites

- Python 3.10 or newer. All included Python tools use the standard library.
- Azure CLI, signed in to the intended tenant and subscription.
- Permission to deploy at subscription scope, create the dedicated resource group
  and manage the selected networking and monitoring resources. Subscription
  Contributor or suitable equivalent permissions are normally needed.
- Capacity, quota and Azure Policy approval for the selected regions and SKUs.

Installation references:

- [Azure CLI on macOS](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-macos)
- [Azure CLI on Linux](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-linux)
- [Python](https://www.python.org/downloads/)

The provisioning commands use compiled ARM templates through core Azure CLI
deployment commands. No CLI extensions or Bicep installation are required for
the supplied deployment. Changing Bicep source requires recompilation using
standalone Bicep or `az bicep`; the build command restores the pinned AVM modules.

## 1. Sign in

From the repository directory:

```bash
python3 --version
az version
az login --use-device-code
az account list --query "[?state=='Enabled'].{Name:name,Id:id}" --output table
```

The wizard selects the subscription explicitly. Deployment does not rely on
your Azure CLI default subscription.

## 2. Configure

```bash
python3 scripts/multi-hub-core/configure.py
```

Choose the subscription by number. Set a new dedicated resource group, vWAN,
hub regions and non-overlapping private prefixes. Select inspection, firewall
tier, policy mode, monitoring and optional gateways. Review all settings, then
confirm saving. This writes `multi-hub.local.json`; Azure resources are unchanged.

Enter `?` at a region prompt to list region codes. Region listing establishes a
valid location name, not capacity or service availability. Check selected zones
and resource availability for each region. Gateways add charges and are disabled
by default.

Check hub ranges against workload VNets and all reachable on-premises networks.
An address prefix cannot be changed after the hub is created. New secured hubs
in this package require `/22` or larger; unsecured hubs accept `/24` or larger.

## 3. Review locally and in Azure

```bash
python3 scripts/multi-hub-core/deploy.py --config multi-hub.local.json
python3 scripts/multi-hub-core/deploy.py --config multi-hub.local.json --what-if
```

Local preview validates configuration and writes generated parameters without
Azure calls. Azure what-if checks the subscription and region names, checks
resource group ownership, and previews the subscription deployment including
resource group creation. A failed what-if exits unsuccessfully. Review its
output before proceeding; what-if does not guarantee allocation capacity.

For an additional Azure template check:

```bash
python3 scripts/multi-hub-core/deploy.py --config multi-hub.local.json --validate-azure
```

An existing empty resource group is accepted only with
`--use-existing-empty-group`, using the same location as `virtualWanLocation`.
Supply that flag for both Azure preview and execution. Existing unrelated or
non-empty groups are refused.

## 4. Execute

```bash
python3 scripts/multi-hub-core/deploy.py --config multi-hub.local.json --execute
```

Keep the terminal open and allow tens of minutes. This creates the dedicated
resource group and core infrastructure. Azure must report `Succeeded` before
the script reports provisioning success. The terminal prints workbook links,
and `multi-hub.local.outputs.json` retains the output mappings.

Private recovery state is stored beneath
`~/.local/share/elrehan-vwan-core/<deployment-id>/state.json` before deployment.
Retain it with your configuration until lab removal completes. No credentials
are stored in that record.

## 5. Inspect and test

Confirm each hub has successful provisioning and provisioned routing in Azure.
Confirm the expected policy is attached to each firewall, diagnostics point to
the shared workspace and each workbook selects its own firewall. Then follow
[manual workload testing](MANUAL-TESTING.md).

## Interrupted provisioning

If a command fails or the terminal closes, Azure may continue provisioning.
Inspect the named `academy-core-<deployment-id>` subscription deployment first.
The script retains resource ownership and local state; it does not roll back or
claim cleanup succeeded.

Retry a recorded unfinished deployment only after it has stopped, using unchanged
settings and the same package:

```bash
python3 scripts/multi-hub-core/deploy.py --config multi-hub.local.json --execute --resume
```

The provisioning tool refuses to redeploy a successfully completed environment.
This protects workload rules and workbook changes made after provisioning.
Infrastructure changes require a separate reviewed update process. After verified
lab removal, a fresh deployment with the original settings is supported.

## Portal deployment

The portal form deploys the resource-group template. It uses a dedicated new
resource group and supplies the hub and policy settings through the form.
See the [portal guide](../MULTI-HUB-PORTAL.md).

The consolidated workbook is additional to the per-hub workbooks and selects
all deployed firewalls by default.
