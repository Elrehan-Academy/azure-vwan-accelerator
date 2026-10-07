targetScope = 'resourceGroup'

@description('Name of the Standard Virtual WAN.')
@minLength(1)
param virtualWanName string

@description('Location of the Virtual WAN resource.')
param virtualWanLocation string = resourceGroup().location

@description('Name of the virtual hub.')
@minLength(1)
param hubName string

@description('Azure region for the hub.')
param hubLocation string = resourceGroup().location

@description('Hub IPv4 CIDR. Must not overlap connected networks; /24 or larger.')
param hubAddressPrefix string

@description('Disabled creates no firewall. FirewallOnly creates a firewall without routing intent. Other modes enable the selected inspection paths.')
@allowed([
  'Disabled'
  'FirewallOnly'
  'Private'
  'Internet'
  'Both'
])
param inspectionMode string = 'Both'

@description('Name of the firewall.')
param firewallName string = '${hubName}-fw'

@description('Firewall and policy tier. Premium features require additional configuration.')
@allowed([
  'Standard'
  'Premium'
])
param firewallTier string = 'Standard'

@description('Number of firewall public IP addresses.')
@minValue(1)
@maxValue(100)
param firewallPublicIpCount int = 1

@description('Firewall availability zones. Select supported zones for the hub region.')
param firewallZones (1 | 2 | 3)[] = []

@description('Name of the firewall policy created by this blueprint.')
param firewallPolicyName string = '${hubName}-policy'

@description('Policy location, independently configurable from the hub location.')
param firewallPolicyLocation string = hubLocation

@description('Threat intelligence action.')
@allowed([
  'Alert'
  'Deny'
  'Off'
])
param threatIntelMode string = 'Deny'

@description('Enable firewall DNS proxy.')
param enableDnsProxy bool = false

@description('Firewall rule collection groups. An empty policy provides no explicit Allow rules.')
param firewallRuleCollectionGroups array = []

@description('Create a workspace and enable firewall diagnostics when a firewall is deployed.')
param enableLogging bool = true

@description('Name of the Log Analytics workspace created by this blueprint.')
param workspaceName string = '${hubName}-logs'

@description('Azure region for the Log Analytics workspace.')
param workspaceLocation string = hubLocation

@description('Log retention in days.')
@minValue(30)
@maxValue(730)
param logRetentionDays int = 30

@description('Resource tags such as owner, environment, and cost centre.')
param tags object = {}

var firewallEnabled = inspectionMode != 'Disabled'
var loggingEnabled = firewallEnabled && enableLogging
var privateInspection = inspectionMode == 'Private' || inspectionMode == 'Both'
var internetInspection = inspectionMode == 'Internet' || inspectionMode == 'Both'

module policy '../../modules/firewall-policy.bicep' = if (firewallEnabled) {
  name: 'single-hub-policy'
  params: {
    name: firewallPolicyName
    location: firewallPolicyLocation
    tier: firewallTier
    threatIntelMode: threatIntelMode
    enableDnsProxy: enableDnsProxy
    ruleCollectionGroups: firewallRuleCollectionGroups
    tags: tags
  }
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = if (loggingEnabled) {
  name: workspaceName
  location: workspaceLocation
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: logRetentionDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: false
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

var secureHub = firewallEnabled ? union({
  deploySecureHub: true
  azureFirewallName: firewallName
  azureFirewallSku: firewallTier
  azureFirewallPublicIPCount: firewallPublicIpCount
  availabilityZones: firewallZones
  firewallPolicyResourceId: policy!.outputs.resourceId
}, privateInspection || internetInspection ? {
  routingIntent: {
    privateToFirewall: privateInspection
    internetToFirewall: internetInspection
  }
} : {}) : {
  deploySecureHub: false
}

module network '../../modules/network.bicep' = {
  name: 'single-hub-network'
  params: {
    virtualWanName: virtualWanName
    virtualWanLocation: virtualWanLocation
    hubs: [
      {
        hubName: hubName
        hubLocation: hubLocation
        hubAddressPrefix: hubAddressPrefix
        secureHubParameters: secureHub
        expressRouteParameters: {
          deployExpressRouteGateway: false
        }
        s2sVpnParameters: {
          deployS2SVpnGateway: false
        }
        p2sVpnParameters: {
          deployP2SVpnGateway: false
        }
      }
    ]
    tags: tags
  }
}

resource firewall 'Microsoft.Network/azureFirewalls@2025-05-01' existing = {
  name: firewallName
}

resource firewallDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (loggingEnabled) {
  name: 'firewall-observability'
  scope: firewall
  properties: {
    workspaceId: workspace!.id
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
  dependsOn: [
    network
  ]
}

output virtualWanResourceId string = network.outputs.virtualWanResourceId
output virtualHubs array = network.outputs.virtualHubs
output firewallResourceId string = firewallEnabled ? firewall.id : ''
output firewallPolicyResourceId string = firewallEnabled ? policy!.outputs.resourceId : ''
output workspaceResourceId string = loggingEnabled ? workspace!.id : ''
output selectedInspectionMode string = inspectionMode
