targetScope = 'resourceGroup'

@description('Name of the firewall policy.')
@minLength(1)
param name string

@description('Azure region for the policy, independently selected from hub locations.')
param location string

@description('Policy tier. The blueprint will match this to the firewall tier.')
@allowed([
  'Standard'
  'Premium'
])
param tier string = 'Standard'

@description('Threat intelligence action.')
@allowed([
  'Alert'
  'Deny'
  'Off'
])
param threatIntelMode string = 'Deny'

@description('Enable the firewall DNS proxy.')
param enableDnsProxy bool = false

@description('Optional parent Firewall Policy resource ID. Null creates an independent policy.')
param basePolicyResourceId string?

@description('Firewall rule collection groups.')
param ruleCollectionGroups array = []

@description('Resource tags.')
param tags object = {}

module policy 'br/public:avm/res/network/firewall-policy:0.3.6' = {
  name: 'policy-${uniqueString(resourceGroup().id, name)}'
  params: {
    name: name
    location: location
    tier: tier
    basePolicyResourceId: basePolicyResourceId
    threatIntelMode: threatIntelMode
    enableProxy: enableDnsProxy
    ruleCollectionGroups: ruleCollectionGroups
    tags: tags
    enableTelemetry: false
  }
}

output resourceId string = policy.outputs.resourceId
output policyLocation string = policy.outputs.location
