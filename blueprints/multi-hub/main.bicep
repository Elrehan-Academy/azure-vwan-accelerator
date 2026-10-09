targetScope = 'resourceGroup'

@sealed()
type hubConfiguration = {
  hubName: string
  hubLocation: string
  hubAddressPrefix: string
  inspectionMode: ('Disabled' | 'FirewallOnly' | 'Private' | 'Internet' | 'Both')?
  firewallName: string?
  firewallPolicyName: string?
  firewallPolicyLocation: string?
  @minValue(1)
  @maxValue(80)
  firewallPublicIpCount: int?
  firewallZones: ((1 | 2 | 3)[])?
  ruleCollectionGroups: array?
  tags: object?
  s2sVpnParameters: object?
  expressRouteParameters: object?
}


@description('Name of the Standard Virtual WAN.')
@minLength(1)
param virtualWanName string

@description('Location of the Virtual WAN resource.')
param virtualWanLocation string = resourceGroup().location

@description('Two to four hub configurations. Each requires hubName, hubLocation and hubAddressPrefix. Optional hub tags override common tags.')
@minLength(2)
@maxLength(4)
param hubs hubConfiguration[]

@description('Shared: one policy. Separate: independent policies. ParentChildren: common parent with a child policy per secured hub.')
@allowed([
  'Shared'
  'Separate'
  'ParentChildren'
])
param policyMode string = 'ParentChildren'

@description('Firewall and policy tier used across secured hubs.')
@allowed([
  'Standard'
  'Premium'
])
param firewallTier string = 'Standard'

@description('Name of the shared policy or common parent policy.')
param commonPolicyName string = '${virtualWanName}-policy'

@description('Location for the shared or parent policy.')
param commonPolicyLocation string = virtualWanLocation

@description('Rules for the shared policy or common parent. Separate mode uses only per-hub rules.')
param commonRuleCollectionGroups array = []

@description('Threat intelligence action.')
@allowed([
  'Alert'
  'Deny'
  'Off'
])
param threatIntelMode string = 'Deny'

@description('Enable DNS proxy on created policies.')
param enableDnsProxy bool = false

@description('Common resource tags. Per-hub tags override matching keys.')
param tags object = {}

@description('Enable firewall diagnostics in a shared Log Analytics workspace.')
param enableLogging bool = true

@description('Name of the shared Log Analytics workspace.')
param workspaceName string = '${virtualWanName}-logs'

@description('Location of the shared workspace.')
param workspaceLocation string = virtualWanLocation

@description('Workspace log retention in days.')
@minValue(30)
@maxValue(730)
param logRetentionDays int = 30

@description('Create a workbook for each enabled firewall when logging is enabled.')
param enableWorkbook bool = true

@description('Workbook display-name prefix. Each workbook also includes its hub name.')
param workbookDisplayNamePrefix string = 'Azure vWAN - Firewall Observability'

var configuredHubs = [for hub in hubs: {
  hubName: hub.hubName
  hubLocation: hub.hubLocation
  hubAddressPrefix: hub.hubAddressPrefix
  inspectionMode: hub.?inspectionMode ?? 'Both'
  firewallName: hub.?firewallName ?? '${hub.hubName}-fw'
  firewallPolicyName: hub.?firewallPolicyName ?? '${hub.hubName}-policy'
  firewallPolicyLocation: hub.?firewallPolicyLocation ?? hub.hubLocation
  firewallPublicIpCount: hub.?firewallPublicIpCount ?? 1
  firewallZones: hub.?firewallZones ?? []
  ruleCollectionGroups: hub.?ruleCollectionGroups ?? []
  tags: union(tags, hub.?tags ?? {})
}]

var securedHubs = filter(configuredHubs, hub => hub.inspectionMode != 'Disabled')
var commonPolicyEnabled = policyMode != 'Separate' && length(securedHubs) > 0

module commonPolicy '../../modules/firewall-policy.bicep' = if (commonPolicyEnabled) {
  name: 'multi-hub-common-policy'
  params: {
    name: commonPolicyName
    location: commonPolicyLocation
    tier: firewallTier
    threatIntelMode: threatIntelMode
    enableDnsProxy: enableDnsProxy
    ruleCollectionGroups: commonRuleCollectionGroups
    tags: tags
  }
}

@batchSize(1)
module hubPolicies '../../modules/firewall-policy.bicep' = [for hub in securedHubs: if (policyMode != 'Shared') {
  name: 'multi-hub-policy-${uniqueString(resourceGroup().id, hub.hubName)}'
  params: {
    name: hub.firewallPolicyName
    location: hub.firewallPolicyLocation
    tier: firewallTier
    threatIntelMode: threatIntelMode
    enableDnsProxy: enableDnsProxy
    basePolicyResourceId: policyMode == 'ParentChildren' ? commonPolicy!.outputs.resourceId : null
    ruleCollectionGroups: hub.ruleCollectionGroups
    tags: hub.tags
  }
}]

var networkHubs = [for (hub, index) in configuredHubs: {
  hubName: hub.hubName
  hubLocation: hub.hubLocation
  hubAddressPrefix: hub.hubAddressPrefix
  tags: hub.tags
  secureHubParameters: hub.inspectionMode == 'Disabled' ? {
    deploySecureHub: false
  } : union({
    deploySecureHub: true
    azureFirewallName: hub.firewallName
    azureFirewallSku: firewallTier
    azureFirewallPublicIPCount: hub.firewallPublicIpCount
    availabilityZones: hub.firewallZones
    firewallPolicyResourceId: policyMode == 'Shared'
      ? resourceId('Microsoft.Network/firewallPolicies', commonPolicyName)
      : resourceId('Microsoft.Network/firewallPolicies', hub.firewallPolicyName)
  }, hub.inspectionMode == 'FirewallOnly' ? {} : {
    routingIntent: {
      privateToFirewall: contains(['Private', 'Both'], hub.inspectionMode)
      internetToFirewall: contains(['Internet', 'Both'], hub.inspectionMode)
    }
  })
  s2sVpnParameters: hubs[index].?s2sVpnParameters ?? {
    deployS2SVpnGateway: false
  }
  expressRouteParameters: hubs[index].?expressRouteParameters ?? {
    deployExpressRouteGateway: false
  }
  p2sVpnParameters: {
    deployP2SVpnGateway: false
  }
}]

module network '../../modules/network.bicep' = {
  name: 'multi-hub-network'
  params: {
    virtualWanName: virtualWanName
    virtualWanLocation: virtualWanLocation
    hubs: networkHubs
    tags: tags
  }
  dependsOn: [
    commonPolicy
    hubPolicies
  ]
}


var loggingEnabled = enableLogging && length(securedHubs) > 0

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


resource firewalls 'Microsoft.Network/azureFirewalls@2025-05-01' existing = [for hub in securedHubs: {
  name: hub.firewallName
}]

resource firewallDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = [for (hub, index) in securedHubs: if (loggingEnabled) {
  name: 'firewall-observability'
  scope: firewalls[index]
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
}]

module observability '../../modules/observability/main.bicep' = [for (hub, index) in securedHubs: if (loggingEnabled && enableWorkbook) {
  name: 'multi-hub-observability-${uniqueString(resourceGroup().id, hub.hubName)}'
  params: {
    workbookName: guid(resourceGroup().id, virtualWanName, hub.hubName, 'firewall-observability')
    location: workspaceLocation
    workspaceResourceId: workspace!.id
    firewallResourceId: firewalls[index].id
    displayName: '${workbookDisplayNamePrefix} - ${hub.hubName}'
    tags: hub.tags
  }
  dependsOn: [
    firewallDiagnostics
  ]
}]

output virtualWanResourceId string = network.outputs.virtualWanResourceId
output virtualHubs array = network.outputs.virtualHubs
output selectedPolicyMode string = policyMode
output workspaceResourceId string = loggingEnabled ? workspace!.id : ''
output firewallResourceIds array = [for hub in securedHubs: resourceId('Microsoft.Network/azureFirewalls', hub.firewallName)]
output workbookResourceIds array = [for (hub, index) in securedHubs: loggingEnabled && enableWorkbook ? observability[index]!.outputs.resourceId : '']
