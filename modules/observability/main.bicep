targetScope = 'resourceGroup'

@description('Stable GUID identifying the workbook.')
param workbookName string

@description('Azure region for the workbook.')
param location string

@description('Log Analytics workspace used by the workbook.')
param workspaceResourceId string

@description('Default selected firewall. The viewer can select other accessible firewalls.')
param firewallResourceId string

@description('Workbook display name.')
param displayName string = 'Azure vWAN - Firewall Observability'

@description('Resource tags.')
param tags object = {}

var workbookData = replace(
  replace(
    loadTextContent('firewall-workbook.json'),
    '__WORKSPACE_RESOURCE_ID__',
    workspaceResourceId
  ),
  '__FIREWALL_RESOURCE_ID__',
  firewallResourceId
)

resource workbook 'Microsoft.Insights/workbooks@2022-04-01' = {
  name: workbookName
  location: location
  kind: 'shared'
  tags: tags
  properties: {
    displayName: displayName
    serializedData: workbookData
    version: '1.0'
    sourceId: toLower(workspaceResourceId)
    category: 'workbook'
  }
}

output resourceId string = workbook.id
output portalUrl string = 'https://portal.azure.com/#resource${workbook.id}'
