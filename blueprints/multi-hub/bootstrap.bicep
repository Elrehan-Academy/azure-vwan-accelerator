targetScope = 'subscription'

@description('Dedicated deployment resource group.')
param resourceGroupName string
param resourceGroupLocation string
@description('Validated core deployment parameters produced by scripts/core.py.')
param coreParameters object

resource deploymentGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: resourceGroupLocation
  tags: coreParameters.tags
}

module core './main.bicep' = {
  name: 'vwan-core-${uniqueString(resourceGroupName, coreParameters.virtualWanName)}'
  scope: deploymentGroup
  params: {
    virtualWanName: coreParameters.virtualWanName
    virtualWanLocation: coreParameters.virtualWanLocation
    hubs: coreParameters.hubs
    policyMode: coreParameters.policyMode
    firewallTier: coreParameters.firewallTier
    commonPolicyName: coreParameters.commonPolicyName
    commonPolicyLocation: coreParameters.commonPolicyLocation
    commonRuleCollectionGroups: coreParameters.commonRuleCollectionGroups
    threatIntelMode: coreParameters.threatIntelMode
    enableDnsProxy: coreParameters.enableDnsProxy
    tags: coreParameters.tags
    enableLogging: coreParameters.enableLogging
    workspaceName: coreParameters.workspaceName
    workspaceLocation: coreParameters.workspaceLocation
    logRetentionDays: coreParameters.logRetentionDays
    enableWorkbook: coreParameters.enableWorkbook
    workbookDisplayNamePrefix: coreParameters.workbookDisplayNamePrefix
  }
}

output resourceGroupResourceId string = deploymentGroup.id
output virtualWanResourceId string = core.outputs.virtualWanResourceId
output hubResources array = core.outputs.hubResources
output selectedPolicyMode string = core.outputs.selectedPolicyMode
output consolidatedWorkbookResourceId string = core.outputs.consolidatedWorkbookResourceId
output consolidatedWorkbookUrl string = core.outputs.consolidatedWorkbookUrl
