# Elrehan Academy — Multi-Hub portal deployment

Deploy the Multi-Hub core infrastructure using the Azure portal form. Create application VNets, workloads, hub connections and workload firewall rules separately after deployment.

## Deployment scope and cost

Use a new, dedicated resource group. The deployment creates one Standard Virtual WAN and two to four regional hubs. Secured hubs also create an Azure Firewall and policy. Gateways are optional and disabled by default. Azure resources and log ingestion incur charges.

## Configure the deployment

1. Select the subscription, new resource group and resource group location.
2. Enter the Virtual WAN name, select its region and choose two, three or four hubs.
3. Choose the policy mode and firewall tier.
4. Configure each selected hub's name, region, private /22 prefix and inspection mode. Optional VPN and ExpressRoute gateways are configured per hub.
5. Choose shared logging, workspace region and retention. Enable workbooks to create one per secured hub and one consolidated All Firewalls workbook.
6. Review the hub/firewall and policy regions separately. Use Azure's review and validation before selecting Create.
7. Wait until deployment succeeds, then check hub routing state, routing intent, diagnostics and workbook access.

## Policy modes

| Mode | Policy configuration |
|---|---|
| ParentChildren | One parent and one child per secured hub. All policies use the selected parent policy region automatically. |
| Shared | One shared policy in the selected common policy region. |
| Separate | Independent policies, each using its selected policy region. |

Firewall policy resources may be stored in a different region from the hub and firewall. Parent and child policies must share the same region. The review page displays both locations.

## Hub prefixes and names

The portal form uses aligned RFC1918 /22 prefixes. Equal-size aligned prefixes overlap only when identical, so duplicate-prefix validation prevents overlap between the selected hubs. Confirm prefixes against every other reachable network as well. Code-based configuration supports additional prefix sizes through its validation tools.

Hub names must be unique, including when compared without case. Firewall, child policy and gateway names are derived from the hub name. A generated child policy name must differ from the parent policy name.

## Inspection and gateways

Both creates Internet and Private routing intent pointing to the local hub firewall. Private and Internet enable the selected inspection path. FirewallOnly creates a firewall without routing intent. Disabled creates an unsecured hub.

Firewall zones are optional; availability depends on region and subscription. Premium features such as IDPS require additional configuration. VPN branch connections and ExpressRoute circuit connections are configured separately. Set ExpressRoute maximum scale units to at least the minimum.

## Workbooks and manual validation

All firewall diagnostics use one shared Log Analytics workspace. The per-hub workbooks select their own firewall. The consolidated workbook selects all deployed firewalls by default. Viewers can change the selected firewalls using the approved workbook's resource picker.

Workbook assessment starts as Not assessed. Provisioning does not generate traffic, correlate Allow/Deny logs or provide a completed NIST assessment. Create workloads separately and verify routing and logs before relying on the deployment for your scenario.

## Removal

For a portal deployment, inspect the dedicated resource group and remove it through Azure when finished. Resource group deletion also removes its workbooks and workspace logs; save any required evidence first.

The CLI ownership-checked removal script applies to deployments made through the CLI with a retained local state file. A portal deployment does not create that local CLI state file.

## Local authoring checks

```bash
python3 scripts/multi-hub-core/build-form.py
python3 scripts/multi-hub-core/check-form.py
```

These commands generate and check local files without Azure calls. Offline validation does not replace previewing the form in Azure or validating its deployment template.

The All Firewalls workbook displays a consolidated Not assessed notice rather
than an aggregate score. Per-hub assessment snapshots remain scoped to their
selected firewall. Workbook customization for Multi-Hub uses its own assets.
