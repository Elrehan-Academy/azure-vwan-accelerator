targetScope = 'resourceGroup'

@description('Object ID of the test execution managed identity.')
param principalId string

@description('Built-in role IDs to assign in this resource group.')
param roleIds array

resource assignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for roleId in roleIds: {
    name: guid(resourceGroup().id, principalId, roleId)
    properties: {
      roleDefinitionId: subscriptionResourceId(
        'Microsoft.Authorization/roleDefinitions', roleId
      )
      principalId: principalId
      principalType: 'ServicePrincipal'
    }
  }
]
