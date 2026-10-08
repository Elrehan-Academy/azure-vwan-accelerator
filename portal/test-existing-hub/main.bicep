targetScope = 'resourceGroup'

@description('Resource group containing the existing virtual hub and firewall.')
param coreResourceGroup string

@description('Existing secured virtual hub name.')
param hubName string

param firewallPolicyResourceId string
param workspaceResourceId string

@description('Hub and test VM region.')
param location string

@description('Resource group containing the firewall policy.')
param policyResourceGroup string = coreResourceGroup

@description('Resource group containing the Log Analytics workspace.')
param workspaceResourceGroup string = coreResourceGroup

param vmSize string = 'Standard_B1ms'
param spokeAPrefix string = '10.251.0.0/24'
param spokeBPrefix string = '10.252.0.0/24'
param adminUsername string = 'harnessadmin'
param publishReport bool = false
param cleanupAfter bool = true

@description('Use a new value to request a new execution.')
param runId string = utcNow()

var testResourceGroupName = 'rg-vwan-probes-${uniqueString(resourceGroup().id)}'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'vwan-test-runner'
  location: location
}

module testScope 'modules/test-scope.bicep' = {
  name: 'test-scope'
  scope: subscription()
  params: {
    testResourceGroupName: testResourceGroupName
    location: location
    principalId: identity.properties.principalId
    automationResourceGroupName: resourceGroup().name
  }
}

module coreAccess 'modules/rg-access.bicep' = {
  name: 'core-network-access'
  scope: resourceGroup(coreResourceGroup)
  params: {
    principalId: identity.properties.principalId
    roleIds: [
      '4d97b98b-1d4f-4787-a291-c67834d212e7'
    ]
  }
}

module policyAccess 'modules/rg-access.bicep' = if (policyResourceGroup != coreResourceGroup) {
  name: 'policy-network-access'
  scope: resourceGroup(policyResourceGroup)
  params: {
    principalId: identity.properties.principalId
    roleIds: [
      '4d97b98b-1d4f-4787-a291-c67834d212e7'
    ]
  }
}

module logAccess 'modules/rg-access.bicep' = {
  name: 'workspace-log-access'
  scope: resourceGroup(workspaceResourceGroup)
  params: {
    principalId: identity.properties.principalId
    roleIds: [
      '73c42c96-874c-492b-b04d-ab87d138a893'
    ]
  }
}

module workbookAccess 'modules/rg-access.bicep' = if (publishReport) {
  name: 'workbook-access'
  scope: resourceGroup(coreResourceGroup)
  params: {
    principalId: identity.properties.principalId
    roleIds: [
      'e8ddcd69-c73f-4f9f-9844-4100522f16ad'
    ]
  }
}

var config = {
  subscriptionId: subscription().subscriptionId
  coreResourceGroup: coreResourceGroup
  hubName: hubName
  expectedPolicyId: firewallPolicyResourceId
  expectedWorkspaceId: workspaceResourceId
  location: location
  testResourceGroup: testResourceGroupName
  vmSize: vmSize
  spokeAPrefix: spokeAPrefix
  spokeBPrefix: spokeBPrefix
  adminUsername: adminUsername
}

var bundle = base64(string(loadJsonContent('scriptBundle.json')))
var chunkSize = 20000
var bundleEnvironment = [
  for index in range(0, (length(bundle) + chunkSize - 1) / chunkSize): {
    name: 'HARNESS_BUNDLE_${index}'
    value: substring(
      bundle,
      index * chunkSize,
      min(chunkSize, length(bundle) - index * chunkSize)
    )
  }
]

var runnerContent = '''
set -euo pipefail
az config set extension.use_dynamic_install=no
az extension add --name virtual-wan --allow-preview true --only-show-errors
az extension add --name azure-firewall --allow-preview true --only-show-errors
az extension add --name log-analytics --allow-preview true --only-show-errors
python3 - <<'PY'
${loadTextContent('portal-run.py')}
PY
'''

resource runner 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  name: 'vwan-existing-hub-tests'
  location: location
  kind: 'AzureCLI'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    azCliVersion: '2.64.0'
    timeout: 'PT4H'
    retentionInterval: 'PT24H'
    cleanupPreference: 'OnExpiration'
    forceUpdateTag: runId
    scriptContent: runnerContent
    environmentVariables: concat([
      {
        name: 'HARNESS_CONFIG'
        value: base64(string(config))
      }
      {
        name: 'HARNESS_CONTROL_RG'
        value: resourceGroup().name
      }
      {
        name: 'HARNESS_BUNDLE_COUNT'
        value: string(length(bundleEnvironment))
      }
      {
        name: 'HARNESS_PUBLISH_REPORT'
        value: string(publishReport)
      }
      {
        name: 'HARNESS_CLEANUP_AFTER'
        value: string(cleanupAfter)
      }
    ], bundleEnvironment)
  }
  dependsOn: [
    testScope
    coreAccess
    policyAccess
    logAccess
    workbookAccess
  ]
}

output testResourceGroup string = testResourceGroupName
output executionResourceId string = runner.id
output result object = runner.properties.outputs
output evidenceRetention string = 'Download evidence within 24 hours after execution finishes.'
output managedIdentityId string = identity.id
