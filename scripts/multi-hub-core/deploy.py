#!/usr/bin/env python3
"""Preview, validate or provision core infrastructure. Does not create workloads."""
import argparse
import json
import sys
from pathlib import Path
from core import ROOT, VERSION, az, deployment_id, digest, load_config, ownership_tags, parameters, print_summary, require, state_path, verify_subscription, write_private


def bootstrap_parameters(c):
    return {'$schema': 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#',
            'contentVersion': '1.0.0.0', 'parameters': {
                'resourceGroupName': {'value': c['resourceGroup']},
                'resourceGroupLocation': {'value': c['virtualWanLocation']},
                'coreParameters': {'value': {k: v['value'] for k, v in parameters(c)['parameters'].items()}},
            }}


def group_gate(c, state, allow_empty=False):
    """Reject adoption of unrelated resources; an empty RG requires explicit opt-in."""
    sub, rg = c['subscriptionId'], c['resourceGroup']
    if not az(['group', 'exists', '--name', rg], sub):
        return
    group = az(['group', 'show', '--name', rg], sub)
    require(group.get('properties', {}).get('provisioningState') != 'Deleting', 'Resource group is deleting.')
    require(group.get('location') == c['virtualWanLocation'],
            'Existing resource group location differs from virtualWanLocation. Use a new group or matching location.')
    owned = all((group.get('tags') or {}).get(k) == v for k, v in ownership_tags(c).items())
    resources = az(['resource', 'list', '--resource-group', rg], sub)
    if owned:
        require(state is not None and state.get('deploymentId') == deployment_id(c),
                'Owned group exists but local deployment state is missing. Restore state; do not adopt automatically.')
        return
    require(allow_empty and not resources, 'Resource group is not owned by this package. Use a new group, or --use-existing-empty-group for an empty one.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='multi-hub.local.json')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--what-if', action='store_true', help='Read-only Azure deployment preview, including a new resource group.')
    mode.add_argument('--validate-azure', action='store_true', help='Azure template validation; no deployment.')
    mode.add_argument('--execute', action='store_true', help='Create billable core resources.')
    parser.add_argument('--use-existing-empty-group', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Retry a recorded unfinished deployment with unchanged parameters.')
    args = parser.parse_args()
    require(not args.resume or args.execute, '--resume requires --execute.')
    c = load_config(args.config)
    print_summary(c)
    p = bootstrap_parameters(c)
    path = Path(args.config).expanduser().resolve().with_suffix('.parameters.json')
    write_private(path, p)
    template = ROOT / 'portal/multi-hub/bootstrapTemplate.json'
    require(template.is_file(), 'Compiled template missing; run scripts/multi-hub-core/build.py.')
    print('Parameters saved:', path)
    if not (args.execute or args.what_if or args.validate_azure):
        print('PASS: local configuration validation. No Azure calls or resource changes.')
        print('Use --what-if for Azure preview, then --execute to deploy.')
        return
    verify_subscription(c)
    state_file = state_path(c)
    state = json.loads(state_file.read_text()) if state_file.exists() else None
    if state:
        require(state.get('deploymentId') == deployment_id(c), 'Local ownership state differs.')
    group_gate(c, state, args.use_existing_empty_group)
    if state and state.get('status') == 'Removed':
        require(not az(['group', 'exists', '--name', c['resourceGroup']], c['subscriptionId']), 'Removed group name is now in use; choose a new group.')
        if args.execute:
            write_private(state_file.with_name('previous-removed-state.json'), state)
            state = None
    param_hash = digest(p)
    template_hash = digest(json.loads(template.read_text()))
    deployment_name = 'academy-core-' + deployment_id(c)
    common = ['--name', deployment_name, '--location', c['virtualWanLocation'],
              '--template-file', str(template), '--parameters', '@' + str(path)]
    if args.what_if:
        az(['deployment', 'sub', 'what-if', *common], c['subscriptionId'], timeout=900, stream=True)
        print('PASS: Azure what-if completed. No resources deployed.')
        return
    if args.validate_azure:
        az(['deployment', 'sub', 'validate', *common], c['subscriptionId'], timeout=900)
        print('PASS: Azure template validation. Capacity and live provisioning remain unverified.')
        return
    if state:
        require(state.get('status') != 'Succeeded',
                'This core deployment already succeeded. Updates are outside this provisioning workflow; review policy/workbook changes separately.')
        require(args.resume and state.get('parametersHash') == param_hash and state.get('templateHash') == template_hash,
                'An unfinished deployment is recorded. Use --resume with the unchanged config and package, or inspect/remove it first.')
        previous = next((d for d in az(['deployment', 'sub', 'list'], c['subscriptionId']) if d.get('name') == deployment_name), None) if state.get('submitted') else None
        require(not previous or previous.get('properties', {}).get('provisioningState') not in ('Running', 'Accepted'),
                'A previous deployment is still running. Wait and inspect it before retrying.')
    else:
        state = {'deploymentId': deployment_id(c), 'packageVersion': VERSION,
                 'subscriptionId': c['subscriptionId'], 'resourceGroup': c['resourceGroup'],
                 'deploymentName': deployment_name, 'parametersHash': param_hash, 'templateHash': template_hash,
                 'ownershipTags': ownership_tags(c), 'configuration': c, 'status': 'Prepared', 'submitted': False}
    # Save ownership and recovery information before the first mutation.
    state.update(status='Submitting', submitted=False)
    write_private(state_file, state)
    print('State:', state_file)
    print('Starting deployment. Keep this terminal open; provisioning can take tens of minutes.', flush=True)
    try:
        state.update(status='Deploying', submitted=True)
        write_private(state_file, state)
        az(['deployment', 'sub', 'create', *common], c['subscriptionId'], timeout=10800, stream=True)
        result = az(['deployment', 'sub', 'show', '--name', deployment_name], c['subscriptionId'])
        require(result.get('properties', {}).get('provisioningState') == 'Succeeded', 'Deployment did not report Succeeded.')
        outputs = result.get('properties', {}).get('outputs') or {}
        state.update(status='Succeeded', outputs=outputs)
        write_private(state_file, state)
        write_private(Path(args.config).expanduser().resolve().with_suffix('.outputs.json'), outputs)
    except (RuntimeError, ValueError, OSError, KeyboardInterrupt) as error:
        state['status'] = 'Needs inspection'
        write_private(state_file, state)
        print('Resources may remain, and Azure deployment may still be running. Inspect the deployment before retrying.', file=sys.stderr)
        print('Removal preview: python3 scripts/multi-hub-core/remove.py --config ' + str(Path(args.config).resolve()), file=sys.stderr)
        raise error
    print('PASS: Azure reported successful core provisioning. Traffic enforcement has not been tested.')
    for hub in outputs.get('hubResources', {}).get('value', []):
        print(hub['hubName'], '|', hub['hubResourceId'])
        if hub.get('workbookUrl'):
            print('Workbook:', hub['workbookUrl'])
    print('Next: docs/multi-hub/MANUAL-TESTING.md. Create workload VNets in a separate resource group.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print('FAIL:', error, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nInterrupted. Azure may still be provisioning; inspect before retrying.', file=sys.stderr)
        sys.exit(1)
