"""Shared validation and Azure CLI helpers. Standard library only."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = '0.1.0-rc1'
MODES = ('ParentChildren', 'Shared', 'Separate')
INSPECTIONS = ('Disabled', 'FirewallOnly', 'Private', 'Internet', 'Both')
PARAMETERS = (
    'virtualWanName', 'virtualWanLocation', 'hubs', 'policyMode', 'firewallTier',
    'commonPolicyName', 'commonPolicyLocation', 'commonRuleCollectionGroups',
    'threatIntelMode', 'enableDnsProxy', 'tags', 'enableLogging', 'workspaceName',
    'workspaceLocation', 'logRetentionDays', 'enableWorkbook', 'workbookDisplayNamePrefix',
)
META = {'schemaVersion', 'subscriptionId', 'resourceGroup'}
HUB_FIELDS = {
    'hubName', 'hubLocation', 'hubAddressPrefix', 'inspectionMode', 'firewallName',
    'firewallPolicyName', 'firewallPolicyLocation', 'firewallPublicIpCount',
    'firewallZones', 'ruleCollectionGroups', 'tags', 's2sVpnParameters',
    'expressRouteParameters',
}
PRIVATE = [ipaddress.ip_network(p) for p in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, low, high, label):
    require(type(value) is int and low <= value <= high,
            f'{label} must be an integer from {low} to {high}.')


def boolean(value, label):
    require(type(value) is bool, f'{label} must be true or false.')


def resource_name(value, label):
    require(isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,62}', value))
            and value[-1].isalnum(), f'{label}: use 1–63 characters, start/end with a letter or digit.')
    return value.casefold()


def region(value, label):
    require(isinstance(value, str) and bool(re.fullmatch(r'[a-z0-9]+', value)),
            f'{label} must be an Azure region code, for example westeurope.')


def tag_object(value, label):
    require(isinstance(value, dict) and len(value) <= 45, f'{label} must be an object with at most 45 tags.')
    for key, val in value.items():
        require(isinstance(key, str) and 0 < len(key) <= 512 and isinstance(val, str) and len(val) <= 256,
                f'{label}: tag keys and values must be strings within Azure size limits.')
        require(key.casefold() not in ('academydeploymentid', 'academypackage'),
                f'{label}: ownership tags are reserved.')


def rule_groups(groups, label):
    require(isinstance(groups, list), f'{label} must be an array.')
    seen = set()
    priorities = set()
    for group in groups:
        require(isinstance(group, dict), f'{label}: each rule group must be an object.')
        n = resource_name(group.get('name'), f'{label} group name')
        require(n not in seen, f'{label}: duplicate group name.')
        seen.add(n)
        integer(group.get('priority'), 100, 65000, f'{label} priority')
        require(group['priority'] not in priorities, f'{label}: duplicate group priority.')
        priorities.add(group['priority'])
        require(isinstance(group.get('ruleCollections'), list), f'{label}: ruleCollections must be an array.')
        # Individual rules follow the pinned AVM/ARM schema and are checked by Azure validation.


def gateway(value, kind, label):
    require(isinstance(value, dict), f'{label} must be an object.')
    if kind == 'vpn':
        allowed = {'deployS2SVpnGateway', 'vpnGatewayName', 'vpnGatewayScaleUnit'}
        flag = 'deployS2SVpnGateway'
        name = 'vpnGatewayName'
    else:
        allowed = {'deployExpressRouteGateway', 'expressRouteGatewayName',
                   'autoScaleConfigurationBoundsMin', 'autoScaleConfigurationBoundsMax'}
        flag = 'deployExpressRouteGateway'
        name = 'expressRouteGatewayName'
    require(not set(value) - allowed, f'{label}: unsupported fields {sorted(set(value) - allowed)}.')
    boolean(value.get(flag), f'{label}.{flag}')
    if name in value:
        resource_name(value[name], f'{label}.{name}')
    if value[flag]:
        resource_name(value.get(name), f'{label}.{name}')
    if kind == 'vpn':
        if 'vpnGatewayScaleUnit' in value:
            integer(value['vpnGatewayScaleUnit'], 1, 20, f'{label}.vpnGatewayScaleUnit')
    else:
        lo = value.get('autoScaleConfigurationBoundsMin', 1)
        hi = value.get('autoScaleConfigurationBoundsMax', 2)
        integer(lo, 1, 10, f'{label}.minimum')
        integer(hi, 1, 10, f'{label}.maximum')
        require(hi >= lo, f'{label}: maximum must be at least minimum.')


def normalize(raw, *, for_cleanup=False):
    """Validate once for wizard, preview, what-if and execution; return explicit defaults."""
    require(isinstance(raw, dict), 'Configuration must be a JSON object.')
    require(not set(raw) - set(PARAMETERS) - META,
            f'Unknown configuration fields: {sorted(set(raw) - set(PARAMETERS) - META)}')
    c = json.loads(json.dumps(raw))
    c.setdefault('schemaVersion', 1)
    require(type(c['schemaVersion']) is int and c['schemaVersion'] == 1, 'Unsupported schemaVersion.')
    try:
        uuid.UUID(c.get('subscriptionId', ''))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('subscriptionId must be a subscription GUID.') from None
    rg = c.get('resourceGroup', '')
    require(isinstance(rg, str) and bool(re.fullmatch(r'[A-Za-z0-9_().-]{1,90}', rg))
            and not rg.endswith('.'), 'Invalid resourceGroup name.')
    resource_name(c.get('virtualWanName'), 'virtualWanName')
    region(c.get('virtualWanLocation'), 'virtualWanLocation')
    wan = c['virtualWanName']
    location = c['virtualWanLocation']
    defaults = {
        'policyMode': 'ParentChildren', 'firewallTier': 'Standard',
        'commonPolicyName': wan + '-policy', 'commonPolicyLocation': location,
        'commonRuleCollectionGroups': [], 'threatIntelMode': 'Deny', 'enableDnsProxy': False,
        'tags': {}, 'enableLogging': True, 'workspaceName': wan + '-logs',
        'workspaceLocation': location, 'logRetentionDays': 30, 'enableWorkbook': True,
        'workbookDisplayNamePrefix': 'Azure vWAN - Firewall Observability',
    }
    for key, val in defaults.items():
        c.setdefault(key, val)
    require(c['policyMode'] in MODES, 'Invalid policyMode.')
    require(c['firewallTier'] in ('Standard', 'Premium'), 'Invalid firewallTier.')
    require(c['threatIntelMode'] in ('Off', 'Alert', 'Deny'), 'Invalid threatIntelMode.')
    for key in ('enableDnsProxy', 'enableLogging', 'enableWorkbook'):
        boolean(c[key], key)
    require(not c['enableWorkbook'] or c['enableLogging'], 'Workbooks require logging.')
    integer(c['logRetentionDays'], 30, 730, 'logRetentionDays')
    for key in ('commonPolicyName', 'workspaceName'):
        resource_name(c[key], key)
    require(4 <= len(c['workspaceName']) <= 63 and '_' not in c['workspaceName'] and '.' not in c['workspaceName'],
            'workspaceName must be 4–63 letters, digits or hyphens.')
    for key in ('commonPolicyLocation', 'workspaceLocation'):
        region(c[key], key)
    require(isinstance(c['workbookDisplayNamePrefix'], str) and 1 <= len(c['workbookDisplayNamePrefix']) <= 150,
            'workbookDisplayNamePrefix must contain 1–150 characters.')
    tag_object(c['tags'], 'tags')
    rule_groups(c['commonRuleCollectionGroups'], 'commonRuleCollectionGroups')
    if c['policyMode'] == 'Separate':
        require(not c['commonRuleCollectionGroups'], 'Separate mode cannot use common rules.')
    hubs = c.get('hubs')
    require(isinstance(hubs, list) and 2 <= len(hubs) <= 4, 'Provide two to four hubs.')
    seen_hubs, seen_firewalls, seen_policies, seen_gateways = set(), set(), set(), set()
    networks = []
    secured = 0
    for hub in hubs:
        require(isinstance(hub, dict), 'Each hub must be an object.')
        require(not set(hub) - HUB_FIELDS, f'Unknown hub fields: {sorted(set(hub) - HUB_FIELDS)}')
        n = resource_name(hub.get('hubName'), 'hubName')
        require(n not in seen_hubs, 'Duplicate hub name.')
        seen_hubs.add(n)
        region(hub.get('hubLocation'), 'hubLocation')
        hub.setdefault('inspectionMode', 'Both')
        require(hub['inspectionMode'] in INSPECTIONS, 'Invalid inspectionMode.')
        try:
            network = ipaddress.ip_network(hub.get('hubAddressPrefix', ''), strict=True)
        except ValueError as error:
            raise ValueError(f'{n}: invalid aligned prefix: {error}') from None
        limit = 24 if hub['inspectionMode'] == 'Disabled' else 22
        require(network.version == 4 and network.prefixlen <= limit,
                f'{n}: use IPv4 /{limit} or larger for this hub (secured defaults use /22).')
        require(any(network.subnet_of(p) for p in PRIVATE), f'{n}: use an RFC1918 private prefix.')
        require(not any(network.overlaps(p) for p in networks), 'Hub address prefixes overlap.')
        networks.append(network)
        hub['hubAddressPrefix'] = str(network)
        hub.setdefault('tags', {})
        tag_object(hub['tags'], f'{n}.tags')
        require(len({**c['tags'], **hub['tags']}) + 2 <= 50, f"{n}: combined tags exceed Azure's 50-tag limit.")
        hub.setdefault('ruleCollectionGroups', [])
        rule_groups(hub['ruleCollectionGroups'], f'{n}.ruleCollectionGroups')
        hub.setdefault('firewallPublicIpCount', 1)
        integer(hub['firewallPublicIpCount'], 1, 80, f'{n}.firewallPublicIpCount')
        hub.setdefault('firewallZones', [])
        zones = hub['firewallZones']
        require(isinstance(zones, list) and all(type(z) is int and z in (1, 2, 3) for z in zones)
                and len(set(zones)) == len(zones), f'{n}: zones must be unique integers 1, 2, 3.')
        hub.setdefault('firewallName', hub['hubName'] + '-fw')
        hub.setdefault('firewallPolicyName', hub['hubName'] + '-policy')
        hub.setdefault('firewallPolicyLocation',
                       c['commonPolicyLocation'] if c['policyMode'] == 'ParentChildren'
                       else hub['hubLocation'])
        if not for_cleanup and c['policyMode'] == 'ParentChildren' and hub['inspectionMode'] != 'Disabled':
            require(hub['firewallPolicyLocation'] == c['commonPolicyLocation'],
                    f'{n}: parent and child policies must use the same region.')
        resource_name(hub['firewallName'], f'{n}.firewallName')
        resource_name(hub['firewallPolicyName'], f'{n}.firewallPolicyName')
        region(hub['firewallPolicyLocation'], f'{n}.firewallPolicyLocation')
        if hub['inspectionMode'] == 'Disabled':
            require(not hub['ruleCollectionGroups'], f'{n}: an unsecured hub cannot have firewall rules.')
        else:
            secured += 1
            fw = hub['firewallName'].casefold()
            require(fw not in seen_firewalls, 'Duplicate firewall name.')
            seen_firewalls.add(fw)
            if c['policyMode'] == 'Shared':
                require(not hub['ruleCollectionGroups'], 'Shared mode uses only common rules.')
            else:
                policy = hub['firewallPolicyName'].casefold()
                require(policy not in seen_policies, 'Duplicate per-hub policy name.')
                require(c['policyMode'] != 'ParentChildren' or policy != c['commonPolicyName'].casefold(),
                        'Child policy name conflicts with the parent policy.')
                seen_policies.add(policy)
        for field, kind in (('s2sVpnParameters', 'vpn'), ('expressRouteParameters', 'er')):
            flag = 'deployS2SVpnGateway' if kind == 'vpn' else 'deployExpressRouteGateway'
            hub.setdefault(field, {flag: False})
            gateway(hub[field], kind, f'{n}.{field}')
            if hub[field][flag]:
                key = 'vpnGatewayName' if kind == 'vpn' else 'expressRouteGatewayName'
                gn = (kind, hub[field][key].casefold())
                require(gn not in seen_gateways, 'Duplicate gateway name.')
                seen_gateways.add(gn)
    require(secured > 0 or not c['commonRuleCollectionGroups'], 'Common rules need at least one firewall.')
    return c


def load_config(path):
    return normalize(json.loads(Path(path).expanduser().read_text()))


def deployment_id(c):
    return hashlib.sha256((c['subscriptionId'].lower() + '/' + c['resourceGroup'].lower()
                           + '/' + c['virtualWanName'].lower()).encode()).hexdigest()[:16]


def ownership_tags(c):
    return {'academyDeploymentId': deployment_id(c), 'academyPackage': 'vwan-multi-hub-core'}


def parameters(c):
    c = normalize(c)
    p = {key: {'value': c[key]} for key in PARAMETERS}
    p['tags']['value'] = {**c['tags'], **ownership_tags(c)}
    return {'$schema': 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#',
            'contentVersion': '1.0.0.0', 'parameters': p}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write_private(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    temp.chmod(0o600)
    temp.replace(path)


def state_path(c):
    return Path.home() / '.local/share/elrehan-vwan-core' / deployment_id(c) / 'state.json'


def az(parts, subscription=None, timeout=180, stream=False):
    require(shutil.which('az') is not None, 'Azure CLI is missing. See docs/multi-hub/DEPLOYMENT.md.')
    if parts[:2] == ['account', 'list-locations']:
        require(subscription is not None, 'Region discovery requires a subscription.')
        parts = [
            'rest', '--method', 'get', '--url',
            'https://management.azure.com/subscriptions/' + subscription
            + '/locations?api-version=2022-12-01',
            '--query', 'value',
        ]
    cmd = ['az', *parts]
    if subscription:
        cmd += ['--subscription', subscription]
    cmd += ['--only-show-errors']
    if not stream:
        cmd += ['--output', 'json']
    print('Azure: ' + ' '.join(parts[:4]), flush=True)
    env = dict(os.environ, AZURE_EXTENSION_USE_DYNAMIC_INSTALL='no')
    try:
        result = subprocess.run(cmd, text=True, capture_output=not stream,
                                timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Azure command timed out. An operation may still be running; inspect it before retrying.') from None
    if result.returncode:
        raise RuntimeError((result.stderr or '').strip() if not stream else 'Azure command failed; review output above.')
    return None if stream else json.loads(result.stdout or 'null')


def verify_subscription(c):
    accounts = az(['account', 'list'])
    require(any(a.get('id', '').lower() == c['subscriptionId'].lower() and a.get('state') == 'Enabled'
                for a in accounts), 'Selected subscription is not accessible. Run az login --use-device-code.')
    regions = {r['name'] for r in az(['account', 'list-locations'], c['subscriptionId'])}
    chosen = {c['virtualWanLocation'], c['workspaceLocation'], c['commonPolicyLocation']}
    chosen.update(h['hubLocation'] for h in c['hubs'])
    chosen.update(h['firewallPolicyLocation'] for h in c['hubs'])
    require(chosen <= regions, f'Unknown/unavailable region codes: {sorted(chosen - regions)}')


def print_summary(c):
    secured = [h for h in c['hubs'] if h['inspectionMode'] != 'Disabled']
    print(f"Subscription: {c['subscriptionId']}\nResource group: {c['resourceGroup']}")
    print(f"Virtual WAN: {c['virtualWanName']} ({c['virtualWanLocation']})")
    for h in c['hubs']:
        print(f"  {h['hubName']}: {h['hubLocation']} | {h['hubAddressPrefix']} | {h['inspectionMode']}")
    print(f"Policies: {c['policyMode']} | Firewall tier: {c['firewallTier']}")
    if secured and c['policyMode'] != 'Separate':
        print(f"  Common policy region: {c['commonPolicyLocation']}")
    for h in secured:
        policy_region = (c['commonPolicyLocation'] if c['policyMode'] == 'Shared'
                         else h['firewallPolicyLocation'])
        print(f"  {h['hubName']}: hub/firewall region={h['hubLocation']} | policy region={policy_region}")
    print(f"Billable core: 1 vWAN, {len(c['hubs'])} hubs, {len(secured)} firewalls; logging={c['enableLogging'] and bool(secured)}")
    print(f"Workbooks: {len(secured) + 1 if c['enableLogging'] and c['enableWorkbook'] and secured else 0} (per-hub plus consolidated)")
    for h in c['hubs']:
        if h['s2sVpnParameters']['deployS2SVpnGateway'] or h['expressRouteParameters']['deployExpressRouteGateway']:
            print(f"  Additional billable gateways enabled in {h['hubName']}.")
    print('Workload VNets, VMs, connections and workload allow rules are configured separately.')
