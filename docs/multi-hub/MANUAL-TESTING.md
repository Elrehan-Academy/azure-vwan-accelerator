# Elrehan Academy — Manual workload testing

After core provisioning, create your own workload VNets and VMs, attach them
to the hubs and test your firewall rules. This guide does not deploy an automated
test harness. Use a separate workload resource group so full core lab removal
does not delete your VMs or VNets.

## 1. Confirm the core

In the Azure portal, inspect the selected subscription and core resource group:

1. The Standard Virtual WAN contains all configured hubs.
2. Each hub reports successful provisioning and provisioned routing.
3. Each configured firewall is healthy and has the expected policy attached.
4. ParentChildren has the common parent and the correct child per firewall;
   Shared uses the same policy ID; Separate uses distinct policies.
5. Diagnostics send firewall logs to the selected workspace using resource-specific
   tables. Each deployed workbook opens and defaults to its own firewall.

Use `multi-hub.local.outputs.json` to identify resources and workbook links.
Do not interpret empty traffic charts as a deployment failure before generating
traffic and allowing time for log ingestion.

## 2. Create and attach workloads

For a complete small lab, create two workload VNets with one Linux VM each per
selected hub. Two hubs therefore use four VNets and four VMs. Existing workloads
may be used instead if they support the same tests.

- Use unique private prefixes that overlap neither hub ranges nor other reachable
  networks. Example workload ranges: `10.251.0.0/24`, `10.251.1.0/24`,
  `10.252.0.0/24`, `10.252.1.0/24`. Check them against your environment.
- Put each VM in a workload subnet. Public IPs and SSH exposure are not required;
  Azure VM Run Command can be used to start listeners and run probes.
- Give VM management traffic and DNS the access they require. Once a spoke is
  attached to an Internet-inspected hub with empty firewall rules, its outbound
  traffic is blocked until you add appropriate rules. Avoid a broad Allow-all rule
  that defeats your Deny tests.
- Inspect workload NSGs and host firewalls. Both test ports must be reachable at
  those layers so Azure Firewall is the intended enforcement point.

Attach each VNet using **Virtual WAN → Virtual network connections → Add**.
Select its intended hub and remote VNet. Use the supported default route-table
association/propagation for routing intent. Enable Internet security/default-route
propagation when that workload should use the hub's Internet inspection.

These are hub virtual network connections. You do not create conventional
VNet-to-VNet peering to the managed hub. The spoke VNet cannot contain its own
VPN/ExpressRoute gateway or Route Server when attached this way.

An optional CLI connection command is:

```bash
az extension add --name virtual-wan
az network vhub connection create \
  --subscription "<subscription-guid>" \
  --resource-group "<core-resource-group>" \
  --vhub-name "<hub-name>" \
  --name "<connection-name>" \
  --remote-vnet "<workload-vnet-resource-id>" \
  --internet-security true
```

Replace every placeholder. Set Internet security according to the chosen
inspection mode and intended workload routing.

## 3. Add narrow workload rules

Record the actual private VM IPs. Create clearly named lab rules in your policy:

| Rule | Source | Destination | Protocol/port | Action |
|---|---|---|---|---|
| `lab-allow-private-8080` | Selected source VM IPs | Selected destination VM IPs | TCP 8080 | Allow |
| `lab-deny-private-8081` | Same test sources | Same test destinations | TCP 8081 | Deny |
| `lab-allow-web-http` | Selected source VM IPs | `www.example.com` | Application HTTP 80 | Allow |
| `lab-deny-web-http` | Same test sources | `www.microsoft.com` | Application HTTP 80 | Deny |

Use separate Allow and Deny rule collections as required by Azure Firewall.
Choose group/collection priorities that do not collide with existing entries.
Check inherited policy and network/application processing order: an existing
Allow rule must not override the Deny test through an earlier matching rule.

For cross-hub traffic, allow the exact remote destination IP in every policy
that inspects the path. In ParentChildren or Separate mode, this usually requires
reviewing both endpoint policies. Shared mode uses a single policy with all
required source/destination pairs. Empty default policies do not allow workloads.

Use Both inspection on the two hubs for the complete matrix below. Disabled,
FirewallOnly and single-path inspection modes require a reduced test scope and
must not be reported as full private-and-Internet inspection validation.

## 4. Prepare listeners and send traffic

On each destination VM, use your application or start an HTTP listener on both
8080 and 8081. One simple method is to run these commands through VM Run Command
or an existing private management session:

```bash
mkdir -p /tmp/vwan-lab-http
printf 'vwan-lab-server\n' > /tmp/vwan-lab-http/index.html
nohup python3 -m http.server 8080 --bind 0.0.0.0 --directory /tmp/vwan-lab-http >/tmp/vwan-lab-8080.log 2>&1 </dev/null &
nohup python3 -m http.server 8081 --bind 0.0.0.0 --directory /tmp/vwan-lab-http >/tmp/vwan-lab-8081.log 2>&1 </dev/null &
curl --noproxy '*' --max-time 5 http://127.0.0.1:8080/
curl --noproxy '*' --max-time 5 http://127.0.0.1:8081/
```

Both local requests must return the expected server content before network tests.
A closed destination port cannot prove firewall denial. If a listener is already
running, inspect it rather than starting another copy.

On each selected source VM, record UTC time and run:

```bash
date -u
curl --noproxy '*' --max-time 15 http://<destination-private-ip>:8080/
curl --noproxy '*' --max-time 15 http://<destination-private-ip>:8081/
curl --noproxy '*' --max-time 15 -i http://www.example.com/
curl --noproxy '*' --max-time 15 -i http://www.microsoft.com/
```

Replace `<destination-private-ip>` with the intended same-hub or remote-hub VM.
Do not follow web redirects for these HTTP tests. Save the output, source/destination
IPs and times for log comparison. A failed request alone does not prove firewall denial; find the matching firewall Deny event.

| Path | Expected test |
|---|---|
| Spoke A → spoke B in each hub | 8080 Allow; 8081 Deny |
| Source VM in each hub → Internet | example.com Allow; microsoft.com Deny |
| Hub 1 workload → hub 2 workload | 8080 Allow; 8081 Deny |
| Hub 2 workload → hub 1 workload | 8080 Allow; 8081 Deny |

For three or four hubs, record which hub pairs and directions you test. Do not
claim validation of pairs you have not exercised.

## 5. Confirm firewall logs and workbooks

Allow several minutes for ingestion. In the shared workspace, query network
and application logs using the actual resource ID, VM IPs and recorded UTC window.
Replace placeholders in these KQL examples:

```kusto
AZFWNetworkRule
| where TimeGenerated between (datetime(<start-utc>) .. datetime(<end-utc>))
| where _ResourceId =~ "<firewall-resource-id>"
| where SourceIp == "<source-private-ip>"
| where DestinationIp == "<destination-private-ip>"
| where DestinationPort in (8080, 8081)
| project TimeGenerated, _ResourceId, SourceIp, DestinationIp, DestinationPort,
          Protocol, Action, RuleCollectionGroup, RuleCollection, Rule
| order by TimeGenerated asc
```

```kusto
AZFWApplicationRule
| where TimeGenerated between (datetime(<start-utc>) .. datetime(<end-utc>))
| where _ResourceId =~ "<firewall-resource-id>"
| where SourceIp == "<source-private-ip>"
| where Fqdn in~ ("www.example.com", "www.microsoft.com")
| project TimeGenerated, _ResourceId, SourceIp, Fqdn, DestinationPort,
          Action, RuleCollectionGroup, RuleCollection, Rule
| order by TimeGenerated asc
```

Correlate action, source, destination/FQDN, port, rule and time with each test.
For a two-hub Both-inspection configuration, Azure documents inspection through
both endpoint security solutions for allowed inter-hub private traffic. A Deny
at an earlier firewall can prevent a later firewall from receiving that packet.
Use effective routing and observed policy decisions to interpret the actual path.

Open each workbook, choose the corresponding firewall and time range, and confirm
the expected network and application events appear. Workbooks visualize telemetry;
they do not independently prove that every test passed.

## Acceptance record

Retain a private record of successful provisioning, policy attachment, diagnostics,
workbook bindings, each traffic result and its matching logs. A complete lab pass
requires the tested paths to behave as expected and the relevant logs to agree.
There is no automatic NIST assessment in this package.

When done, remove your temporary workload rules and resources, or retain them
deliberately for learning. Core removal is separate: [cleanup guide](CLEANUP.md).

References:

- [Connect workload VNets](https://learn.microsoft.com/en-us/azure/virtual-wan/howto-connect-vnet-hub)
- [Routing intent paths and requirements](https://learn.microsoft.com/en-us/azure/virtual-wan/how-to-routing-policies)
- [Network rule log schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/azfwnetworkrule)
- [Application rule log schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/azfwapplicationrule)

## Consolidated view

Open the All Firewalls workbook and select the same test time range. Compare
events from the endpoint firewalls using the workbook's existing resource picker.
Retain the matching resource IDs when investigating cross-hub traffic.
