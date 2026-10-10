# Elrehan Academy — Full lab removal

Review and remove your manual workload rules, hub connections and workload
resources separately. The core package does not track or delete workloads you
created in other resource groups.

Full core removal deletes the package's dedicated resource group, including
vWAN, hubs, firewalls, policies, optional gateways, workbooks and Log Analytics
workspace. Export any logs or evidence you want to keep first.

## Preview the exact scope

```bash
python3 scripts/multi-hub-core/remove.py --config multi-hub.local.json
```

This makes read-only Azure calls and displays the resource group and its resources.
It checks the private deployment state, package ownership tags and expected
resource types/names. It refuses removal if unrelated top-level resources are
present or the deployment is still running. Do not strip ownership tags or lose
the local state file while using this workflow.

## Execute after reviewing

```bash
python3 scripts/multi-hub-core/remove.py --config multi-hub.local.json --execute --delete-resource-group
```

Both flags are required. The tool rechecks resources, requests group deletion,
waits and reports success only after Azure confirms the group is absent.
Deletion can take tens of minutes. If waiting is interrupted, deletion can
continue in Azure; run the removal preview again to inspect the status.

Settings, outputs and local state are retained. After verified removal, the
deployment command can create a fresh environment using the same settings.

If you intentionally changed ownership tags or placed unrelated resources in the
core group, the tool refuses automatic deletion. Review and resolve that situation
in Azure rather than bypassing its checks. Workload VMs and VNets in separate
resource groups remain billable until you remove them.

## Portal deployments

Portal provisioning does not create the CLI's local ownership state file.
For portal-created labs, inspect and remove the dedicated resource group through
Azure. Save required logs first. The CLI cleanup workflow above applies to
CLI-created deployments with their retained state.

The consolidated workbook is included in full core removal.
