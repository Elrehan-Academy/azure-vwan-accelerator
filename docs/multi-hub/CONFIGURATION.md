# Elrehan Academy — Multi-Hub configuration

`multi-hub.local.json` contains the settings collected by the wizard. The CLI tools use the shared configuration validator; the portal form has its own input checks. Unknown fields, conflicting names, overlapping
prefixes, incompatible rules and invalid gateway bounds are rejected.

## Infrastructure settings

| Setting | Default / meaning |
|---|---|
| `subscriptionId`, `resourceGroup` | Selected subscription and dedicated deployment group |
| `virtualWanName`, `virtualWanLocation` | One Standard vWAN and resource location |
| `hubs` | Array of 2–4 hub objects |
| `firewallTier` | `Standard`; optionally `Premium` for all firewalls and policies |
| `policyMode` | `ParentChildren`; alternatives `Shared`, `Separate` |
| `commonPolicyName`, `commonPolicyLocation` | Parent/shared policy name and location |
| `threatIntelMode` | `Deny`; alternatives `Alert`, `Off` |
| `enableDnsProxy` | `false`; configure workload DNS separately if enabled |
| `commonRuleCollectionGroups` | Empty; shared or parent policy rules |
| `enableLogging` | `true`; workspace exists only if at least one firewall exists |
| `workspaceName`, `workspaceLocation` | Shared Log Analytics workspace identity/location |
| `logRetentionDays` | `30`; configurable 30–730 |
| `enableWorkbook` | `true`; requires logging; one workbook per firewall plus one consolidated workbook |
| `workbookDisplayNamePrefix` | Common display prefix followed by the hub name |
| `tags` | Common string tags; package ownership tags are added automatically |

The wizard saves explicit defaults. Advanced rule arrays can be added to the
settings before provisioning. They follow the pinned firewall-policy AVM schema.
Group names and priorities are checked locally; individual rule schema and
platform constraints are checked by Azure validation and what-if.

## Hub settings

Each hub requires `hubName`, `hubLocation` and `hubAddressPrefix`. Optional fields:

- `inspectionMode`: default `Both`.
- `firewallName`, `firewallPolicyName`, `firewallPolicyLocation`: names are derived from the hub; ParentChildren policy regions default to the parent region.
- `firewallPublicIpCount`: 1–80, default 1; quota and regional availability apply.
- `firewallZones`: unique integers from 1, 2, 3; default empty. Availability varies by region.
- `ruleCollectionGroups`: per-hub child/independent rules; default empty.
- `tags`: per-hub overrides of common tags; ownership tags cannot be overridden.
- `s2sVpnParameters` and `expressRouteParameters`: gateway settings below.

| Inspection | Firewall | Private routing intent | Internet routing intent |
|---|---|---|---|
| Disabled | No | No | No |
| FirewallOnly | Yes | No | No |
| Private | Yes | Yes | No |
| Internet | Yes | No | Yes |
| Both | Yes | Yes | Yes |

FirewallOnly provisions the firewall without automatically steering workload
traffic through it. Private and Internet configure the corresponding routing
policies. Both enables both policies. The template does not create workload
connections. Routing intent manages route-table behavior; use the supported
connection settings in the manual guide rather than adding conflicting static
routes or custom route tables.

## Policy modes

| Mode | Policies | Rule placement |
|---|---|---|
| ParentChildren | One common parent plus a child per firewall | Common rules in parent; local rules in child |
| Shared | One policy attached to all firewalls | Only common rules; per-hub arrays must be empty |
| Separate | Independent policy per firewall | Only per-hub rules; common array must be empty |

Parent rules are inherited and have precedence over child rules according to
Azure Firewall rule processing. A child rule cannot be used to override a parent
decision. Review inherited rules when testing traffic. This package deploys
empty rules by default, so inspected traffic requires explicit workload Allow
rules. Disabled hubs cannot have per-hub firewall rules. If every hub is Disabled,
no firewall policies, diagnostics, workspace or workbook are deployed.

## Optional gateways

VPN configuration:

```json
"s2sVpnParameters": {
  "deployS2SVpnGateway": true,
  "vpnGatewayName": "hub-west-vpn",
  "vpnGatewayScaleUnit": 1
}
```

ExpressRoute configuration:

```json
"expressRouteParameters": {
  "deployExpressRouteGateway": true,
  "expressRouteGatewayName": "hub-west-er",
  "autoScaleConfigurationBoundsMin": 1,
  "autoScaleConfigurationBoundsMax": 2
}
```

Maximum must be at least minimum. VPN allows 1–20 scale units and ExpressRoute
bounds allow 1–10. Creation adds billable gateways; VPN sites, tunnels, circuits
and circuit connections must be configured separately. The core configuration
intentionally does not accept connection credentials.

## Outputs and monitoring

`hubResources` maps every hub to its hub ID, inspection mode, firewall ID, policy
ID, parent policy ID, workspace ID, workbook ID and workbook link. An empty value
indicates that feature was not deployed. Logging uses dedicated firewall tables
in the shared workspace. Workbooks default to their own firewall; retain that
filter when comparing hubs.

No traffic generator or automatic assessment is included. Workbook traffic
views depend on your workloads and log ingestion. Preconfigured assessment
sections are not evidence of compliance.

References:

- [Hub address planning](https://learn.microsoft.com/en-us/azure/virtual-wan/hub-settings)
- [Routing intent](https://learn.microsoft.com/en-us/azure/virtual-wan/how-to-routing-policies)
- [Firewall rule processing](https://learn.microsoft.com/en-us/azure/firewall/rule-processing)
- [Pinned vWAN AVM](https://github.com/Azure/bicep-registry-modules/tree/avm/ptn/network/virtual-wan/0.2.0/avm/ptn/network/virtual-wan)

## Policy regions and consolidated monitoring

Parent and child policy resources must share one Azure region. The CLI wizard
assigns the parent region to child policies automatically and rejects conflicting
manually edited settings. Hub and firewall regions remain independent.

With logging and workbooks enabled, the deployment creates one workbook per
secured hub and one All Firewalls workbook. The consolidated workbook selects
all deployed firewalls. `consolidatedWorkbookResourceId` and
`consolidatedWorkbookUrl` identify it separately from the per-hub output mappings.
Assessment starts as Not assessed.

See the [portal guide](../MULTI-HUB-PORTAL.md) for the portal form.

The All Firewalls workbook displays a consolidated Not assessed notice rather
than an aggregate score. Per-hub assessment snapshots remain scoped to their
selected firewall. Workbook customization for Multi-Hub uses its own assets.
