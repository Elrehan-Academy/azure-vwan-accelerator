#!/usr/bin/env python3
"""Check isolated workbook defaults and query scope without Azure calls."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'modules/observability/multi-hub'

def check():
    workbook = json.loads((FOLDER / 'firewall-workbook.json').read_text())
    parameters = [p for item in workbook['items'] if item.get('type') == 9
                  for p in item['content']['parameters']]
    for name in ('Resource', 'Workspaces', 'AssessmentSnapshot'):
        matches = [p for p in parameters if p['name'] == name]
        if len(matches) != 1:
            raise ValueError(f'Expected exactly one {name} parameter.')
    resource = next(p for p in parameters if p['name'] == 'Resource')
    if resource.get('multiSelect') is not True:
        raise ValueError('Resource picker must support multiple firewalls.')
    for item in workbook['items']:
        query = item.get('content', {}).get('query', '')
        if re.search(r'^AZFW\w+', query, re.M):
            if '{Resource}' not in query and '{Resource:label}' not in query:
                raise ValueError('Unscoped firewall query: ' + item.get('name', 'unnamed'))
    serialized = json.dumps(workbook)
    if re.search(r'/subscriptions/[0-9a-fA-F-]{36}', serialized):
        raise ValueError('Hardcoded subscription resource ID remains.')
    unexpected = set(re.findall(r'__[A-Z_]+__', serialized)) - {
        '__WORKSPACE_RESOURCE_ID__', '__FIREWALL_RESOURCE_ID__'}
    if unexpected:
        raise ValueError('Unexpected placeholders: ' + repr(unexpected))
    # Check both deployment transformations using representative resource IDs.
    workspace = '/subscriptions/test/resourceGroups/lab/providers/Microsoft.OperationalInsights/workspaces/logs'
    ids = ['/subscriptions/test/resourceGroups/lab/providers/Microsoft.Network/azureFirewalls/fw-a',
           '/subscriptions/test/resourceGroups/lab/providers/Microsoft.Network/azureFirewalls/fw-b']
    per_hub = serialized.replace('__WORKSPACE_RESOURCE_ID__', workspace).replace('__FIREWALL_RESOURCE_ID__', ids[0])
    single = json.loads(per_hub)
    snapshot = next(p for i in single['items'] if i['type'] == 9
                    for p in i['content']['parameters'] if p['name'] == 'AssessmentSnapshot')
    if json.loads(snapshot['value'])['firewallId'] != ids[0]:
        raise ValueError('Per-hub assessment firewall scope differs.')
    consolidated = json.loads(serialized)
    consolidated['items'] = [i for i in consolidated['items']
                             if '{AssessmentSnapshot}' not in i.get('content', {}).get('query', '')]
    for item in consolidated['items']:
        if item.get('type') == 9:
            for parameter in item['content']['parameters']:
                if parameter['name'] == 'Resource': parameter['value'] = ids
                if parameter['name'] == 'Workspaces': parameter['value'] = [workspace]
    rendered = json.dumps(consolidated).replace('__WORKSPACE_RESOURCE_ID__', workspace).replace('__FIREWALL_RESOURCE_ID__', '')
    if re.search(r'__[A-Z_]+__', rendered):
        raise ValueError('Unresolved placeholder remains after transformation.')
    source = (FOLDER / 'consolidated.bicep').read_text()
    for required in ('snapshotItems', 'retainedItems', 'assessmentNotice', 'Not assessed.'):
        if required not in source:
            raise ValueError('Consolidated assessment transformation missing: ' + required)
    print('PASS: workbook parameters, query scope, resource defaults and assessment separation.')

if __name__ == '__main__':
    check()
