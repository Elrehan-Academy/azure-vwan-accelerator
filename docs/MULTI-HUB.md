# Multi-Hub deployment — draft

## Validation status

The Bicep blueprint compiles. Three policy-mode examples pass offline
configuration checks. Negative tests verify rejection of overlapping hub
prefixes, duplicate hub names, invalid inspection modes, parent/child name
conflicts and per-hub rules in Shared mode.

No complete Multi-Hub Azure deployment or cross-hub traffic test has been
performed. There is no published Multi-Hub deployment button.

## Microsoft module foundation

The blueprint reuses these pinned Azure Verified Modules through wrappers:

- Virtual WAN: `avm/ptn/network/virtual-wan:0.2.0`
- Firewall Policy: `avm/res/network/firewall-policy:0.3.6`

Published sources and examples:

- https://github.com/Azure/bicep-registry-modules/tree/main/avm/ptn/network/virtual-wan
- https://github.com/Azure/bicep-registry-modules/tree/main/avm/res/network/firewall-policy

AVM module validation does not validate this custom composition.

## Supported draft configuration

- Two to four hubs in one Standard Virtual WAN.
- Resources deployed into one resource group.
- Independently selected hub regions and non-overlapping IPv4 prefixes.
- One selected firewall tier, Standard or Premium, across secured hubs.
- Per-hub inspection: Disabled, FirewallOnly, Private, Internet or Both.
- Optional site-to-site VPN and ExpressRoute gateway configuration.
- Point-to-site gateways are not exposed by this blueprint.
- Common tags merged with per-hub tags; per-hub values take precedence.
- One shared Log Analytics workspace.
- Diagnostics and a separate workbook for each enabled firewall.

Premium selection alone does not configure TLS inspection or IDPS.

## Firewall selection per hub

Each hub independently selects `inspectionMode`:

| Mode | Behavior |
| --- | --- |
| Disabled | Hub without a firewall or firewall routing intent |
| FirewallOnly | Firewall without routing intent |
| Private | Inspect private traffic |
| Internet | Inspect Internet traffic |
| Both | Inspect private and Internet traffic |

Disabled hubs receive no per-hub firewall policy, firewall diagnostics or
workbook. A common policy and shared workspace are created only when the
selected settings require them and at least one firewall is enabled.

Disabling a hub's firewall removes inspection from that hub; review the
routing design before mixing secured and unsecured hubs.

On an existing deployment, changing a mode to Disabled does not
automatically delete previously created resources. Removal requires an
explicit reviewed cleanup operation.

## Policy modes

| Mode | Created policies | Rule inputs |
| --- | --- | --- |
| Shared | One policy attached to all enabled firewalls | Common rules |
| Separate | Independent policy per enabled firewall | Per-hub rules |
| ParentChildren | Common parent and child per enabled firewall | Common parent rules plus per-hub child rules |

ParentChildren is the default. The parent is inherited by each child;
the child is attached to its firewall. Parent rules have precedence within
the same rule type. Scope parent rules carefully.

The validator rejects common rules in Separate mode and per-hub rules
in Shared mode to avoid silently ignoring configuration.

## Offline configuration validation

Choose one example from `blueprints/multi-hub/`:

- `shared.example.parameters.json`
- `separate.example.parameters.json`
- `parentchildren.example.parameters.json`

Run from the repository root:

    python3 scripts/validation/validate-multi-hub.py blueprints/multi-hub/parentchildren.example.parameters.json

Compile without deploying:

    az bicep build --file blueprints/multi-hub/main.bicep --stdout > /dev/null

The validator runs explicitly; a direct Azure deployment does not invoke it.
Bicep types validate hub fields and inspection modes. The Python validator
adds naming, prefix and policy-mode checks. Neither guarantees permissions,
regional capability, quota, live capacity or complete rule validity.

## Remaining work before release

- Validate all policy modes and disabled-firewall combinations in Azure.
- Validate gateway settings and region-specific zone support.
- Check compiled template compatibility with the Azure portal.
- Add the Multi-Hub portal form only after validation.
- Verify cross-hub routing and matching Allow/Deny logs.
- Extend the CLI test workflow for cross-hub probes.
- Add explicit workbook selection to the report publisher: it currently
  expects one workbook per workspace and cannot publish to this layout.
- Assess inherited policies before reporting policy-scope checks as complete.
- Document updates, expansion and resource removal.

The existing CLI test guide remains a Single Hub workflow. Do not assume
its complete test and publication flow supports Multi-Hub yet.
