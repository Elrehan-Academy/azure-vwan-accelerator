#!/usr/bin/env python3
"""Collect core settings; no Azure writes."""
import argparse
import json
import shlex
import sys
from pathlib import Path
from core import INSPECTIONS, MODES, az, normalize, print_summary, write_private


def ask(label, default):
    return input(f'{label} [{default}]: ').strip() or str(default)


def number(label, default, low, high):
    while True:
        try:
            value = int(ask(label, default))
            if low <= value <= high:
                return value
        except ValueError:
            pass
        print(f'Enter an integer from {low} to {high}.')


def yes(label, default=False):
    while True:
        v = input(f"{label} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
        if not v:
            return default
        if v in ('y', 'yes', 'n', 'no'):
            return v in ('y', 'yes')
        print('Enter y or n.')


def choose(label, items, display=str, default=None):
    if not items:
        raise ValueError(f'No available {label}.')
    print('\n' + label)
    for i, item in enumerate(items, 1):
        print(f'  {i}. {display(item)}')
    return items[number('Choose a number', default or 1, 1, len(items)) - 1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='multi-hub.local.json')
    args = parser.parse_args()
    path = Path(args.config).expanduser().resolve()
    print('Elrehan Academy — Multi-Hub core configuration')
    print('Azure discovery is read-only. Saving changes only a local settings file.')
    if path.exists() and not yes('Replace saved settings after reviewing new settings?'):
        return
    accounts = [a for a in az(['account', 'list']) if a.get('state') == 'Enabled']
    sub = choose('Subscription', accounts, lambda a: a['name'] + ' — ' + a['id'])
    locations = sorted(az(['account', 'list-locations'], sub['id']), key=lambda r: r['name'])
    region_names = {r['name'] for r in locations}

    def location(label, default):
        while True:
            v = ask(label + ' (region code; ? lists regions)', default).lower()
            if v == '?':
                print(', '.join(sorted(region_names)))
            elif v in region_names:
                return v
            else:
                print('Choose a listed Azure region code.')

    c = {'schemaVersion': 1, 'subscriptionId': sub['id'],
         'resourceGroup': ask('New dedicated resource group', 'rg-vwan-multi-hub'),
         'virtualWanName': ask('Virtual WAN name', 'vwan-multi'),
         'virtualWanLocation': location('Virtual WAN region', 'westeurope')}
    count = number('Number of hubs', 2, 2, 4)
    hubs = []
    defaults = ('westeurope', 'northeurope', 'eastus', 'westus2')
    for i in range(count):
        print(f'\nHub {i + 1}/{count}')
        h = {'hubName': ask('Hub name', f'hub-{i + 1:02d}'),
             'hubLocation': location('Hub region', defaults[i]),
             'inspectionMode': choose('Inspection mode', INSPECTIONS, default=5),
             'hubAddressPrefix': ask('Non-overlapping hub prefix (/22 for secured hubs)', f'10.250.{i * 4}.0/22')}
        if h['inspectionMode'] != 'Disabled':
            h['firewallPublicIpCount'] = number('Firewall public IP count', 1, 1, 80)
            while True:
                try:
                    z = input('Firewall zones (comma-separated 1,2,3; blank = no zone selection): ').strip()
                    zones = [int(v.strip()) for v in z.split(',')] if z else []
                    if any(v not in (1, 2, 3) for v in zones) or len(zones) != len(set(zones)):
                        raise ValueError()
                    h['firewallZones'] = zones
                    break
                except ValueError:
                    print('Enter unique zone numbers, or leave blank.')
        vpn = yes('Create site-to-site VPN gateway?')
        h['s2sVpnParameters'] = {'deployS2SVpnGateway': vpn}
        if vpn:
            h['s2sVpnParameters'].update(vpnGatewayName=ask('VPN gateway name', h['hubName'] + '-vpn'),
                                         vpnGatewayScaleUnit=number('VPN scale units', 1, 1, 20))
        er = yes('Create ExpressRoute gateway?')
        h['expressRouteParameters'] = {'deployExpressRouteGateway': er}
        if er:
            lo = number('ExpressRoute minimum scale units', 1, 1, 10)
            hi = number('ExpressRoute maximum scale units', max(2, lo), lo, 10)
            h['expressRouteParameters'].update(expressRouteGatewayName=ask('ExpressRoute gateway name', h['hubName'] + '-er'),
                autoScaleConfigurationBoundsMin=lo, autoScaleConfigurationBoundsMax=hi)
        hubs.append(h)
    c['hubs'] = hubs
    secured = any(h['inspectionMode'] != 'Disabled' for h in hubs)
    c['policyMode'] = choose('Policy mode', MODES) if secured else 'ParentChildren'
    if secured:
        if c['policyMode'] == 'ParentChildren':
            c['commonPolicyLocation'] = location('Parent and child policy region', c['virtualWanLocation'])
            print('Parent and child policies must share one region.')
            print('Hub and firewall regions remain independent.')
            for h in hubs:
                if h['inspectionMode'] != 'Disabled':
                    h['firewallPolicyLocation'] = c['commonPolicyLocation']
        elif c['policyMode'] == 'Shared':
            c['commonPolicyLocation'] = location('Shared policy region', c['virtualWanLocation'])
            print('This policy can protect firewalls in different regions.')
        else:
            for h in hubs:
                if h['inspectionMode'] != 'Disabled':
                    h['firewallPolicyLocation'] = location(
                        h['hubName'] + ' policy region', h['hubLocation'])
    c['firewallTier'] = choose('Firewall tier', ('Standard', 'Premium')) if secured else 'Standard'
    c['enableLogging'] = yes('Enable firewall logging?', True) if secured else False
    c['enableWorkbook'] = yes('Create one workbook per firewall?', True) if c['enableLogging'] else False
    if secured:
        c['threatIntelMode'] = choose('Threat intelligence', ('Deny', 'Alert', 'Off'))
        c['enableDnsProxy'] = yes('Enable firewall DNS proxy?')
    if c['enableLogging']:
        c['workspaceName'] = ask('Shared workspace name', c['virtualWanName'] + '-logs')
        c['workspaceLocation'] = location('Workspace region', c['virtualWanLocation'])
        c['logRetentionDays'] = number('Retention days', 30, 30, 730)
    c['tags'] = {'environment': ask('Environment tag', 'lab'), 'owner': ask('Owner tag', 'elrehan-academy')}
    try:
        c = normalize(c)
    except ValueError as error:
        print(f'Configuration not saved: {error}')
        print('Rerun the wizard to correct the settings.')
        return 1
    print('\nReview settings')
    print_summary(c)
    print(json.dumps(c, indent=2))
    print('Check these prefixes against all reachable VNets and on-premises networks.')
    if yes('Save settings?'):
        write_private(path, c)
        print('Saved:', path)
        cmd = 'python3 scripts/multi-hub-core/deploy.py --config ' + shlex.quote(str(path))
        print('Local preview:', cmd)
        print('Azure preview:', cmd + ' --what-if')
        print('Deployment:', cmd + ' --execute')
        print('No Azure resources created or modified.')


if __name__ == '__main__':
    try:
        sys.exit(main() or 0)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print('FAIL:', error, file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print('\nStopped; no settings saved.', file=sys.stderr)
        sys.exit(1)
