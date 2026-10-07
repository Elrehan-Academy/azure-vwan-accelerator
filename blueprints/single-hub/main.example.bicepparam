using './main.bicep'

// Example configuration. Review names and address ranges before deployment.
param virtualWanName = 'vwan-example'
param virtualWanLocation = 'westeurope'
param hubName = 'vhub-example-weu'
param hubLocation = 'westeurope'
param hubAddressPrefix = '10.250.0.0/24'

param tags = {
  environment: 'example'
  owner: 'replace-with-service-owner'
  cost_center: 'replace-with-cost-centre'
}

// Security and monitoring settings
// Modes: Disabled, FirewallOnly, Private, Internet, Both.
param inspectionMode = 'Both'
param firewallName = 'afw-example-weu'
param firewallTier = 'Standard'
param firewallPublicIpCount = 1
param firewallZones = []

param firewallPolicyName = 'afwp-example'
param firewallPolicyLocation = 'westeurope'
param threatIntelMode = 'Deny'
param enableDnsProxy = false

// Add approved rules before connecting workload networks.
// Empty means no explicit Allow rules.
param firewallRuleCollectionGroups = []

param enableLogging = true
param workspaceName = 'log-example-weu'
param workspaceLocation = 'westeurope'
param logRetentionDays = 30
