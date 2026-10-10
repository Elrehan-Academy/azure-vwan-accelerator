targetScope = 'resourceGroup'

param workbookName string
param location string
param workspaceResourceId string
@minLength(1)
param firewallResourceIds array
param displayName string
param tags object = {}

var approvedWorkbook = loadJsonContent('firewall-workbook.json')
var snapshotItems = filter(approvedWorkbook.items, item => item.type == 3 && contains(item.content.?query ?? '', '{AssessmentSnapshot}'))
var retainedItems = filter(approvedWorkbook.items, item => !contains(snapshotItems, item))
var assessmentNotice = {
  type: 1
  name: 'multi-hub-assessment-notice'
  content: {
    json: '## Consolidated assessment\n**Not assessed.** This workbook combines firewall telemetry. A verified assessment must identify each firewall and its evidence; no aggregate NIST score is supplied by provisioning.'
  }
  conditionalVisibility: {
    parameterName: 'selectedTab'
    comparison: 'isEqualTo'
    value: 'AcademyAssessment'
  }
}
var configuredItems = map(concat(retainedItems, [assessmentNotice]), item => item.type == 9 ? union(item, {
  content: union(item.content, {
    parameters: map(item.content.parameters, p => p.name == 'Resource' ? union(p, {
      value: firewallResourceIds
    }) : p.name == 'Workspaces' ? union(p, {
      value: [
        workspaceResourceId
      ]
    }) : p)
  })
}) : item)

var workbookData = replace(
  replace(
    string(union(approvedWorkbook, { items: configuredItems })),
    '__WORKSPACE_RESOURCE_ID__',
    workspaceResourceId
  ),
  '__FIREWALL_RESOURCE_ID__',
  ''
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
