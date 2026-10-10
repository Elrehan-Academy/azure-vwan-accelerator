#!/usr/bin/env python3
"""Review or remove a recorded, package-owned core resource group."""
import argparse
import json
import sys
import time
from core import az, deployment_id, load_config, normalize, ownership_tags, require, state_path, write_private


def allowed_resources(c, state, resources):
    """Refuse to delete unrelated top-level resources even if the RG is owned."""
    expected = {
        'microsoft.network/virtualwans': {c['virtualWanName'].casefold()},
        'microsoft.network/virtualhubs': {h['hubName'].casefold() for h in c['hubs']},
        'microsoft.network/azurefirewalls': {h['firewallName'].casefold() for h in c['hubs'] if h['inspectionMode'] != 'Disabled'},
        'microsoft.network/firewallpolicies': set(),
        'microsoft.operationalinsights/workspaces': set(),
        'microsoft.insights/workbooks': set(),
        'microsoft.network/vpngateways': {h['s2sVpnParameters']['vpnGatewayName'].casefold() for h in c['hubs'] if h['s2sVpnParameters']['deployS2SVpnGateway']},
        'microsoft.network/expressroutegateways': {h['expressRouteParameters']['expressRouteGatewayName'].casefold() for h in c['hubs'] if h['expressRouteParameters']['deployExpressRouteGateway']},
    }
    secured = [h for h in c['hubs'] if h['inspectionMode'] != 'Disabled']
    if secured:
        if c['policyMode'] != 'Separate':
            expected['microsoft.network/firewallpolicies'].add(c['commonPolicyName'].casefold())
        if c['policyMode'] != 'Shared':
            expected['microsoft.network/firewallpolicies'].update(h['firewallPolicyName'].casefold() for h in secured)
        if c['enableLogging']:
            expected['microsoft.operationalinsights/workspaces'].add(c['workspaceName'].casefold())
    hub_outputs = state.get('outputs', {}).get('hubResources', {}).get('value', [])
    workbook_ids = {h.get('workbookResourceId', '').casefold() for h in hub_outputs if h.get('workbookResourceId')}
    consolidated_id = state.get('outputs', {}).get('consolidatedWorkbookResourceId', {}).get('value', '')
    if consolidated_id:
        workbook_ids.add(consolidated_id.casefold())
    blocked = []
    for r in resources:
        typ, name = r['type'].casefold(), r['name'].casefold()
        if typ == 'microsoft.resources/deployments':
            continue
        owned = all((r.get('tags') or {}).get(k) == v for k, v in ownership_tags(c).items())
        if typ == 'microsoft.insights/workbooks':
            permitted = c['enableLogging'] and c['enableWorkbook'] and bool(secured)
            # Successful deployment supplies exact IDs; partial runs require ownership tags.
            permitted = permitted and (not hub_outputs or r['id'].casefold() in workbook_ids)
        else:
            permitted = name in expected.get(typ, set())
        if not owned or not permitted:
            blocked.append(r['id'])
    require(not blocked, 'Unrelated or unowned resources found; removal refused:\n' + '\n'.join(blocked))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='multi-hub.local.json')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--delete-resource-group', action='store_true', help='Explicitly authorize full removal of the displayed core RG.')
    args = parser.parse_args()
    require(not args.execute or args.delete_resource_group, 'Execution requires both --execute and --delete-resource-group.')
    c = load_config(args.config)
    path = state_path(c)
    require(path.is_file(), 'Local deployment state is missing. Restore the state file; automatic removal is refused.')
    state = json.loads(path.read_text())
    require(state.get('deploymentId') == deployment_id(c) and state.get('resourceGroup', '').casefold() == c['resourceGroup'].casefold()
            and state.get('subscriptionId', '').casefold() == c['subscriptionId'].casefold(), 'State ownership differs from configuration.')
    require(isinstance(state.get('configuration'), dict), 'Original configuration is missing from state; removal refused.')
    c = normalize(state['configuration'], for_cleanup=True)
    require(deployment_id(c) == state['deploymentId'], 'Recorded configuration ownership is inconsistent.')
    print('FULL CORE REMOVAL:', c['resourceGroup'], '|', c['subscriptionId'])
    print('Includes vWAN, hubs, firewalls, policies, gateways, workbooks and workspace logs.')
    sub, rg = c['subscriptionId'], c['resourceGroup']
    if not az(['group', 'exists', '--name', rg], sub):
        state['status'] = 'Removed'
        write_private(path, state)
        print('PASS: core resource group already absent. Local records retained.')
        return
    group = az(['group', 'show', '--name', rg], sub)
    require(all((group.get('tags') or {}).get(k) == v for k, v in ownership_tags(c).items()), 'Resource group ownership tags differ; refusing removal.')
    deployments = az(['deployment', 'sub', 'list'], sub)
    running = [d for d in deployments if d.get('name') == state['deploymentName'] and d.get('properties', {}).get('provisioningState') in ('Running', 'Accepted')]
    require(not running, 'Core deployment is still running. Wait or cancel it in Azure before removal.')
    resources = az(['resource', 'list', '--resource-group', rg], sub)
    for r in resources:
        print('  ' + r['type'] + ' | ' + r['name'])
    allowed_resources(c, state, resources)
    if not args.execute:
        print('Preview only. No resources deleted.')
        print('Add --execute --delete-resource-group after reviewing the scope.')
        return
    # Re-read immediately before deletion; do not rely solely on the earlier preview.
    allowed_resources(c, state, az(['resource', 'list', '--resource-group', rg], sub))
    az(['group', 'delete', '--name', rg, '--yes', '--no-wait'], sub)
    deadline = time.monotonic() + 7200
    while time.monotonic() < deadline:
        if not az(['group', 'exists', '--name', rg], sub):
            state['status'] = 'Removed'
            write_private(path, state)
            print('PASS: Azure confirms core resource group is absent. Local settings and records retained.')
            return
        print('Deletion in progress. Waiting 20 seconds...', flush=True)
        time.sleep(20)
    raise RuntimeError('Deletion is still pending after two hours. Inspect Azure; do not assume completion.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print('FAIL:', error, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nStopped waiting. Azure deletion may continue; verify before redeploying.', file=sys.stderr)
        sys.exit(1)
