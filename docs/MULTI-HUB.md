# Elrehan Academy — Multi-Hub deployment

Provision two to four Azure Virtual WAN hubs with optional firewall inspection,
parent/child, shared or separate policies, shared logging and optional gateways.
Create workload VNets, hub connections and traffic tests separately.

Gateways are disabled by default. Parent/child policy resources share one region;
hub and firewall regions can differ. With monitoring enabled, one workbook per
secured hub and one consolidated All Firewalls workbook use the shared workspace.

- [Portal deployment](MULTI-HUB-PORTAL.md)
- [CLI deployment](multi-hub/DEPLOYMENT.md)
- [Configuration](multi-hub/CONFIGURATION.md)
- [Manual workload testing](multi-hub/MANUAL-TESTING.md)
- [Cleanup](multi-hub/CLEANUP.md)

Azure resources incur charges. Review settings and validate the deployment in
your subscription before use. Workbook assessment requires separate evidence.

## Separate deployment paths

Single-Hub and Multi-Hub have separate blueprint, portal and script folders.
Multi-Hub workbook assets live in `modules/observability/multi-hub/`; the approved
Single-Hub workbook remains unchanged. Both deployments reuse the pinned network
and firewall-policy modules.

The consolidated workbook shows combined telemetry and an explicit Not assessed
notice. It does not combine individual firewall assessment scores.
