targetScope = 'subscription'

param testResourceGroupName string
param location string
param principalId string
param automationResourceGroupName string

resource testGroup 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: testResourceGroupName
  location: location
  tags: {
    purpose: 'vwan-test-harness'
    automationResourceGroup: automationResourceGroupName
  }
}

resource reader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, principalId, 'vwan-test-reader')
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'acdd72a7-3385-48ef-bd42-f606fba81ae7'
    )
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

module testAccess 'rg-access.bicep' = {
  name: 'test-resource-access'
  scope: resourceGroup(testGroup.name)
  params: {
    principalId: principalId
    roleIds: [
      'b24988ac-6180-42a0-ab88-20f7382dd24c'
    ]
  }
}

output resourceGroupName string = testGroup.name
