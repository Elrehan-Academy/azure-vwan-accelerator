#!/usr/bin/env python3
"""Build the Multi-Hub portal form. No Azure calls."""
import json
from pathlib import Path

SCHEMA = 'https://schema.management.azure.com/schemas/2021-09-09/uiFormDefinition.schema.json#'
NAME = r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,48}[A-Za-z0-9])?$'
OCTET = r'(?:0|[1-9][0-9]?|1[0-9]{2}|2[0-4][0-9]|25[0-5])'
BLOCK = '(?:' + '|'.join(str(i) for i in range(0, 256, 4)) + ')'
PREFIX = r'^(?:10\.' + OCTET + r'|172\.(?:1[6-9]|2[0-9]|3[01])|192\.168)\.' + BLOCK + r'\.0/22$'

def expr(value):
    return '[' + value + ']'

def ref(step, name):
    return "steps('" + step + "')." + name

def info(name, text, visible=True, style='Info'):
    return dict(name=name, type='Microsoft.Common.InfoBox', visible=visible,
                options=dict(style=style, text=text))

def text(name, label, default, regex=NAME, message='Use 1–50 letters, digits or hyphens; start and end with a letter or digit.', validations=None, visible=True):
    checks = [dict(regex=regex, message=message)] if regex else []
    checks += validations or []
    return dict(name=name, type='Microsoft.Common.TextBox', label=label,
                defaultValue=default, visible=visible,
                constraints=dict(required=True, validations=checks))

def dropdown(name, label, choices, default, visible=True):
    return dict(name=name, type='Microsoft.Common.DropDown', label=label,
                defaultValue=default, visible=visible,
                constraints=dict(required=True, allowedValues=[dict(label=l, value=v) for l,v in choices]))

def boolean(name, label, default='false', visible=True):
    return dropdown(name, label, [('Enabled','true'),('Disabled','false')],
                    'Enabled' if default == 'true' else 'Disabled', visible)

def region(name, label, resource_type, visible=True):
    return dict(name=name, type='Microsoft.Common.LocationSelector', label=label,
                resourceTypes=[resource_type], visible=visible,
                scope=dict(subscriptionId=expr(ref('basics','resourceScope.subscription.subscriptionId'))))

def number(step, name, label, default, low, high, extra=None, visible=True):
    r=ref(step,name)
    safe="int(if(empty("+r+"), '0', "+r+"))"
    checks=[dict(isValid=expr(f'and(greaterOrEquals({safe}, {low}), lessOrEquals({safe}, {high}))'),
                 message=f'Enter a whole number from {low} to {high}.')]
    checks += extra or []
    return text(name,label,str(default),r'^[0-9]+$','Enter a whole number.',checks,visible)

def hub_json(i):
    step='hubs'; base=f'hub{i}.'
    def r(k): return ref(step,base+k)
    def numeric(k, default):
        value = r(k)
        return "string(int(if(empty(" + value + "), '" + str(default) + "', " + value + ")))"
    # concat receives strings only; hidden numeric controls use explicit defaults.
    # Return a concat expression, using escaped JSON syntax as single-quoted UI literals.
    pieces=[]
    def literal(s): pieces.append("'"+s.replace("'","''")+"'")
    def field(key,value,quoted=True):
        literal((',' if pieces else '{')+'"'+key+'":'+('"' if quoted else ''))
        pieces.append(value)
        if quoted: literal('"')
    field('hubName',r('hubName'))
    field('hubLocation',"coalesce("+r('hubRegion.name')+", "+ref('basics','resourceScope.location.name')+")")
    field('hubAddressPrefix',r('hubAddressPrefix'))
    field('inspectionMode',r('inspectionMode'))
    field('firewallName',"concat("+r('hubName')+", '-fw')")
    field('firewallPolicyName',"concat("+r('hubName')+", '-policy')")
    field('firewallPolicyLocation',"if(equals("+ref('policies','policyMode')+", 'Separate'), coalesce("+r('policyRegion.name')+", "+r('hubRegion.name')+", "+ref('basics','resourceScope.location.name')+"), coalesce("+ref('policies','commonPolicyRegion.name')+", "+ref('basics','resourceScope.location.name')+"))")
    field('firewallPublicIpCount', numeric('firewallPublicIpCount', 1), False)
    field('firewallZones', "if(empty("+r('firewallZones')+"), '[]', "+r('firewallZones')+")", False)
    literal(',"s2sVpnParameters":{"deployS2SVpnGateway":')
    pieces.append(r('deployVpnGateway'))
    literal(',"vpnGatewayName":"');pieces.append("concat("+r('hubName')+", '-vpn')");literal('","vpnGatewayScaleUnit":')
    pieces.append(numeric('vpnScaleUnits', 1));literal('}')
    literal(',"expressRouteParameters":{"deployExpressRouteGateway":');pieces.append(r('deployExpressRouteGateway'))
    literal(',"expressRouteGatewayName":"');pieces.append("concat("+r('hubName')+", '-er')");literal('","autoScaleConfigurationBoundsMin":')
    pieces.append(numeric('expressRouteMinScaleUnits', 1));literal(',"autoScaleConfigurationBoundsMax":')
    pieces.append(numeric('expressRouteMaxScaleUnits', 2));literal('},"ruleCollectionGroups":[],"tags":{}}')
    return 'concat('+', '.join(pieces)+')'

def build():
    count=ref('network','hubCount')
    mode=ref('policies','policyMode')
    basics=dict(name='basics',label='Basics',elements=[
        dict(name='resourceScope',type='Microsoft.Common.ResourceScope',
             resourceGroup=dict(allowExisting=False),
             location=dict(resourceTypes=['Microsoft.Resources/resourceGroups'])),
        info('introduction','Elrehan Academy — deploy 2–4 regional vWAN hubs with optional firewall inspection and gateways. Workloads and traffic testing are configured separately. Azure resources incur charges. Use a dedicated new resource group.')])
    network=dict(name='network',label='Network',elements=[
        text('virtualWanName','Virtual WAN name','vwan-multi'),
        region('virtualWanRegion','Virtual WAN region','Microsoft.Network/virtualWans'),
        dropdown('hubCount','Number of hubs',[(str(i),str(i)) for i in (2,3,4)],'2'),
        info('prefixHelp','This portal wizard uses aligned private /22 hub prefixes. Each selected hub must have a different prefix. Also check overlap with your connected VNets and on-premises networks. Code-based configuration supports additional validated prefix sizes.')])
    separate=expr("equals("+mode+", 'Separate')")
    common=expr("not(equals("+mode+", 'Separate'))")
    policies=dict(name='policies',label='Policies',elements=[
        dropdown('policyMode','Policy mode',[(x,x) for x in ('ParentChildren','Shared','Separate')],'ParentChildren'),
        info('inheritance','Parent and child policy resources must share one region. Child policy regions are assigned automatically. Hub and firewall regions remain independent.',expr("equals("+mode+", 'ParentChildren')")),
        info('sharedHelp','One shared policy can protect firewalls in different regions.',expr("equals("+mode+", 'Shared')")),
        info('separateHelp','Each secured hub has an independent policy. Select its policy region in that hub section.',separate),
        text('commonPolicyName','Parent / shared policy name',expr("concat("+ref('network','virtualWanName')+", '-policy')"),visible=common),
        region('commonPolicyRegion','Parent / shared policy region','Microsoft.Network/firewallPolicies',common),
        dropdown('firewallTier','Firewall tier',[(x,x) for x in ('Standard','Premium')],'Standard'),
        dropdown('threatIntelMode','Threat intelligence',[(x,x) for x in ('Deny','Alert','Off')],'Deny'),
        boolean('enableDnsProxy','Firewall DNS proxy')])
    hub_sections=[]
    for i in range(1,5):
        base=f'hub{i}.';r=lambda k:ref('hubs',base+k)
        enabled=expr(f'greaterOrEquals(int({count}), {i})')
        secured=expr("not(equals("+r('inspectionMode')+", 'Disabled'))")
        vpn=expr("bool("+r('deployVpnGateway')+")")
        er=expr("bool("+r('deployExpressRouteGateway')+")")
        name_checks=[];prefix_checks=[]
        for j in range(1,i):
            name_checks.append(dict(isValid=expr('not(equals(toLower('+r('hubName')+'), toLower('+ref('hubs',f'hub{j}.hubName')+')))'),message=f'Hub name must differ from Hub {j}.'))
            prefix_checks.append(dict(isValid=expr('not(equals('+r('hubAddressPrefix')+', '+ref('hubs',f'hub{j}.hubAddressPrefix')+'))'),message=f'Hub prefix overlaps Hub {j}; select another aligned /22 prefix.'))
        name_checks.append(dict(isValid=expr("or(not(equals("+mode+", 'ParentChildren')), equals("+r('inspectionMode')+", 'Disabled'), not(equals(toLower(concat("+r('hubName')+", '-policy')), toLower("+ref('policies','commonPolicyName')+"))))"),message='The generated child policy name must differ from the parent policy name.'))
        elements=[
            text('hubName','Hub name',f'hub-{i:02d}',validations=name_checks),
            region('hubRegion','Hub and firewall region','Microsoft.Network/virtualHubs'),
            text('hubAddressPrefix','Hub address prefix',f'10.250.{(i-1)*4}.0/22',PREFIX,'Use an aligned RFC1918 /22 prefix, for example 10.250.4.0/22.',prefix_checks),
            dropdown('inspectionMode','Inspection mode',[(x,x) for x in ('Both','Private','Internet','FirewallOnly','Disabled')],'Both'),
            info('inspectionHelp','Both inspects private and internet traffic. Private or Internet inspects the selected path. FirewallOnly creates a firewall without routing intent. Disabled creates no firewall. Firewall, policy and gateway names are derived from the hub name.'),
            region('policyRegion','Independent policy region','Microsoft.Network/firewallPolicies',expr("and(equals("+mode+", 'Separate'), not(equals("+r('inspectionMode')+", 'Disabled')))")),
            number('hubs',base+'firewallPublicIpCount','Firewall public IP count',1,1,80,visible=secured),
            dropdown('firewallZones','Firewall availability zones',[('No zone selection','[]'),('Zone 1','[1]'),('Zone 2','[2]'),('Zone 3','[3]'),('Zones 1, 2 and 3','[1,2,3]')],'No zone selection',secured),
            boolean('deployVpnGateway','Create site-to-site VPN gateway'),
            number('hubs',base+'vpnScaleUnits','VPN scale units',1,1,20,visible=vpn),
            boolean('deployExpressRouteGateway','Create ExpressRoute gateway'),
            number('hubs',base+'expressRouteMinScaleUnits','ExpressRoute minimum scale units',1,1,10,visible=er),
            number('hubs',base+'expressRouteMaxScaleUnits','ExpressRoute maximum scale units',2,1,10,
                   extra=[dict(isValid=expr('greaterOrEquals(int('+r('expressRouteMaxScaleUnits')+'), int('+r('expressRouteMinScaleUnits')+'))'),message='ExpressRoute maximum must be at least the minimum.')],visible=er)]
        # Control names inside a Section are local; expression references retain section prefixes.
        for e in elements:
            if e['name'].startswith(base): e['name']=e['name'][len(base):]
        hub_sections.append(dict(name=f'hub{i}',type='Microsoft.Common.Section',label=f'Hub {i}',elements=elements,visible=enabled))
    hubs=dict(name='hubs',label='Hubs and gateways',elements=hub_sections)
    logging=expr("bool("+ref('monitoring','enableLogging')+")")
    monitoring=dict(name='monitoring',label='Monitoring',elements=[
        boolean('enableLogging','Firewall logging','true'),
        text('workspaceName','Shared Log Analytics workspace name',expr("concat("+ref('network','virtualWanName')+", '-logs')"),r'^[A-Za-z0-9][A-Za-z0-9-]{2,61}[A-Za-z0-9]$','Use 4–63 letters, digits or hyphens; start/end with a letter or digit.',visible=logging),
        region('workspaceRegion','Shared workspace region','Microsoft.OperationalInsights/workspaces',logging),
        number('monitoring','logRetentionDays','Log retention days',30,30,730,visible=logging),
        boolean('enableWorkbook','Per-hub and consolidated workbooks','true',logging),
        text('workbookDisplayNamePrefix','Workbook display-name prefix','Azure vWAN - Firewall Observability',r'^.{1,100}$','Enter 1–100 characters.',visible=logging),
        info('monitoringHelp','All firewall logs use one shared workspace. Workbooks retain the approved Azure Firewall layout: one per secured hub and one All Firewalls workbook. Assessment starts as Not assessed; provisioning does not create workloads or verify traffic.')])
    secure_terms=[f"if(and(greaterOrEquals(int({count}), {i}), not(equals({ref('hubs',f'hub{i}.inspectionMode')}, 'Disabled'))), 1, 0)" for i in range(1,5)]
    secure_count='add(add('+secure_terms[0]+', '+secure_terms[1]+'), add('+secure_terms[2]+', '+secure_terms[3]+'))'
    book_count="if(and(bool("+ref('monitoring','enableLogging')+"), bool("+ref('monitoring','enableWorkbook')+"), greater("+secure_count+", 0)), add("+secure_count+", 1), 0)"
    review_elements=[info('summary',expr("concat('Review: ', "+count+", ' hubs; ', string("+secure_count+"), ' firewalls; ', "+ref('policies','policyMode')+", ' policies; ', string("+book_count+"), ' workbooks. Azure resources incur charges. Review the template changes before selecting Create.')"),style='Warning')]
    for i in range(1,5):
        r=lambda k:ref('hubs',f'hub{i}.'+k)
        pol="if(equals("+mode+", 'Separate'), coalesce("+r('policyRegion.name')+", "+r('hubRegion.name')+", "+ref('basics','resourceScope.location.name')+"), coalesce("+ref('policies','commonPolicyRegion.name')+", "+ref('basics','resourceScope.location.name')+"))"
        review_elements.append(info(f'hub{i}Review',expr("concat("+r('hubName')+", ' | hub/firewall region: ', coalesce("+r('hubRegion.name')+", "+ref('basics','resourceScope.location.name')+"), ' | prefix: ', "+r('hubAddressPrefix')+", ' | inspection: ', "+r('inspectionMode')+", ' | policy region: ', if(equals("+r('inspectionMode')+", 'Disabled'), 'none', "+pol+"))"),expr(f'greaterOrEquals(int({count}), {i})')))
    review=dict(name='review',label='Review settings',elements=review_elements)
    hub_array="parse(concat('[', "+hub_json(1)+", ',', "+hub_json(2)
    for i in (3,4): hub_array+=", if(greaterOrEquals(int("+count+f"), {i}), concat(',', "+hub_json(i)+"), '')"
    hub_array+=" , ']'))"
    parameters={
        'virtualWanName':expr(ref('network','virtualWanName')),
        'virtualWanLocation':expr("coalesce("+ref('network','virtualWanRegion.name')+", "+ref('basics','resourceScope.location.name')+")"),
        'hubs':expr(hub_array), 'policyMode':expr(mode),
        'firewallTier':expr(ref('policies','firewallTier')),
        'commonPolicyName':expr("if(equals("+mode+", 'Separate'), concat("+ref('network','virtualWanName')+", '-policy'), "+ref('policies','commonPolicyName')+")"),
        'commonPolicyLocation':expr("coalesce("+ref('policies','commonPolicyRegion.name')+", "+ref('basics','resourceScope.location.name')+")"),
        'commonRuleCollectionGroups':[],
        'threatIntelMode':expr(ref('policies','threatIntelMode')),
        'enableDnsProxy':expr("bool("+ref('policies','enableDnsProxy')+")"),
        'tags':{'owner':'elrehan-academy'},
        'enableLogging':expr("bool("+ref('monitoring','enableLogging')+")"),
        'enableWorkbook':expr("and(bool("+ref('monitoring','enableLogging')+"), bool("+ref('monitoring','enableWorkbook')+"))"),
        'workspaceName':expr(ref('monitoring','workspaceName')),
        'workspaceLocation':expr("coalesce("+ref('monitoring','workspaceRegion.name')+", "+ref('basics','resourceScope.location.name')+")"),
        'logRetentionDays':expr("int(if(empty("+ref('monitoring','logRetentionDays')+"), '30', "+ref('monitoring','logRetentionDays')+"))"),
        'workbookDisplayNamePrefix':expr(ref('monitoring','workbookDisplayNamePrefix'))}
    return {'$schema':SCHEMA,'view':{'kind':'Form','properties':{'title':'Elrehan Academy — Azure vWAN Multi-Hub','steps':[basics,network,policies,hubs,monitoring,review]},'outputs':{'kind':'ResourceGroup','location':expr(ref('basics','resourceScope.location.name')),'resourceGroupId':expr(ref('basics','resourceScope.resourceGroup.id')),'parameters':parameters}}}

if __name__ == '__main__':
    root=Path(__file__).resolve().parents[2]
    target=root/'portal/multi-hub/uiFormDefinition.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(build(),indent=2,ensure_ascii=False)+'\n')
    print('Built:',target)
