#!/usr/bin/env python3
"""Offline portal expression and configuration checks; no Azure calls."""
import json
import re
import sys
from pathlib import Path

TOKEN=re.compile(r"\s*('(?:[^']|'')*'|[0-9]+|[A-Za-z_][A-Za-z_0-9]*|[().,])")

class Expression:
    def __init__(self,text):
        self.tokens=[];pos=0
        while pos<len(text):
            match=TOKEN.match(text,pos)
            if not match: raise ValueError('Unsupported expression syntax: '+text[pos:pos+50])
            self.tokens.append(match.group(1));pos=match.end()
        self.pos=0
        self.tree=self.node()
        if self.pos!=len(self.tokens):raise ValueError('Trailing expression tokens')
    def pop(self):
        t=self.tokens[self.pos];self.pos+=1;return t
    def node(self):
        t=self.pop()
        if t.startswith("'"):n=('literal',t[1:-1].replace("''","'"))
        elif t.isdigit():n=('literal',int(t))
        elif t in ('true','false'):n=('literal',t=='true')
        else:
            if self.pop()!='(':raise ValueError('Expected function call')
            args=[]
            if self.tokens[self.pos]!=')':
                while True:
                    args.append(self.node())
                    if self.tokens[self.pos]!=',':break
                    self.pop()
            if self.pop()!=')':raise ValueError('Expected closing parenthesis')
            n=('call',t,args)
        while self.pos<len(self.tokens) and self.tokens[self.pos]=='.':
            self.pop();n=('property',n,self.pop())
        return n
    def evaluate(self,state):
        def ev(n):
            if n[0]=='literal':return n[1]
            if n[0]=='property':
                v=ev(n[1]);return v.get(n[2]) if isinstance(v,dict) else None
            fn=n[1]
            if fn=='if':return ev(n[2][1] if ev(n[2][0]) else n[2][2])
            args=[ev(a) for a in n[2]]
            def s(v):return json.dumps(v,separators=(',',':')) if isinstance(v,(dict,list,bool)) else str(v)
            functions={
                'steps':lambda name:state.get(name,{}),
                'concat':lambda *v:''.join(s(x) for x in v),
                'parse':json.loads,'int':int,'string':s,
                'bool':lambda v:v if isinstance(v,bool) else str(v).lower()=='true',
                'equals':lambda a,b:a==b,'not':lambda v:not v,
                'and':lambda *v:all(v),'or':lambda *v:any(v),
                'greaterOrEquals':lambda a,b:a>=b,'lessOrEquals':lambda a,b:a<=b,
                'greater':lambda a,b:a>b,'add':lambda a,b:a+b,
                'empty':lambda v:v is None or v=='' or v==[] or v=={},
                'toLower':lambda v:str(v).lower(),
                'coalesce':lambda *v:next((x for x in v if x is not None),None)}
            if fn not in functions:raise ValueError('Unsupported function: '+fn)
            return functions[fn](*args)
        return ev(self.tree)

def evaluate(value,state):
    return Expression(value[1:-1]).evaluate(state) if isinstance(value,str) and re.match(r'^\[[A-Za-z_][A-Za-z_0-9]*\(',value) and value.endswith(']') else value

def controls(form):
    for step in form['view']['properties']['steps']:
        for control in step['elements']:
            if control['type']=='Microsoft.Common.Section':
                for child in control['elements']:yield step['name'],control['name'],child
            else:yield step['name'],None,control

def defaults(form):
    state={'basics':{'resourceScope':{'subscription':{'subscriptionId':'00000000-0000-0000-0000-000000000000'},'resourceGroup':{'id':'/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-portal-test'},'location':{'name':'westeurope'}}}}
    for step,section,c in controls(form):
        target=state.setdefault(step,{})
        if section:target=target.setdefault(section,{})
        if c['type'] in ('Microsoft.Common.InfoBox','Microsoft.Common.ResourceScope'):continue
        if c['type']=='Microsoft.Common.LocationSelector':
            target[c['name']]={'name':'northeurope' if step=='hubs' and section=='hub2' else 'westeurope'}
        else:
            value=evaluate(c.get('defaultValue',''),state)
            if c['type']=='Microsoft.Common.DropDown':
                options=c['constraints']['allowedValues']
                value=next((o['value'] for o in options if o['label']==value or o['value']==value),value)
            target[c['name']]=value
    return state

def visible(c,state):return evaluate(c.get('visible',True),state)

def valid(c,value,state):
    for check in c.get('constraints',{}).get('validations',[]):
        if 'regex' in check and not re.fullmatch(check['regex'],str(value)):return False
        if 'isValid' in check and not evaluate(check['isValid'],state):return False
    return True

def check(form,template,normalize):
    assert form['view']['kind']=='Form'
    parameters=form['view']['outputs']['parameters']
    assert set(parameters)==set(template['parameters']), 'Portal/template parameters differ'
    known={}
    for step in form['view']['properties']['steps']:
        assert step['name'] not in known
        known[step['name']]=step
    # Parse all expressions, including constraints, visibility, defaults and review text.
    def walk(v):
        if isinstance(v,dict):
            for x in v.values():walk(x)
        elif isinstance(v,list):
            for x in v:walk(x)
        elif isinstance(v,str) and re.match(r'^\[[A-Za-z_][A-Za-z_0-9]*\(',v) and v.endswith(']'):
            Expression(v[1:-1])
    walk(form)
    tests=0
    for n in (2,3,4):
        for mode in ('ParentChildren','Shared','Separate'):
            for inspection in ('Both','Disabled','FirewallOnly','Private','Internet'):
                for logging in ('true','false'):
                    state=defaults(form);state['network']['hubCount']=str(n);state['policies']['policyMode']=mode
                    state['monitoring']['enableLogging']=logging
                    for i in range(1,5):state['hubs'][f'hub{i}']['inspectionMode']=inspection
                    for step,section,c in controls(form):
                        if section and int(section[-1])>n:continue
                        if not visible(c,state):continue
                        target=state[step][section] if section else state.get(step,{})
                        if c['type']=='Microsoft.Common.TextBox':assert valid(c,target[c['name']],state),c['name']
                        if c['type']=='Microsoft.Common.InfoBox':evaluate(c['options']['text'],state)
                    result={k:evaluate(v,state) for k,v in parameters.items()}
                    config=dict(result,schemaVersion=1,subscriptionId='00000000-0000-0000-0000-000000000000',resourceGroup='rg-portal-test')
                    c=normalize(config)
                    assert len(c['hubs'])==n
                    if mode=='ParentChildren':assert all(h['firewallPolicyLocation']==c['commonPolicyLocation'] for h in c['hubs'])
                    assert c['enableWorkbook']==(logging=='true')
                    tests+=1
    state=defaults(form)
    fields={(s,sec,c['name']):c for s,sec,c in controls(form)}
    state['hubs']['hub2']['hubName']='HUB-01'
    assert not valid(fields['hubs','hub2','hubName'],'HUB-01',state)
    state=defaults(form);state['hubs']['hub2']['hubAddressPrefix']='10.250.0.0/22'
    assert not valid(fields['hubs','hub2','hubAddressPrefix'],'10.250.0.0/22',state)
    prefix=fields['hubs','hub1','hubAddressPrefix']
    for bad in ('10.250.1.0/22','10.250.0.1/22','10.250.0.0/24','8.8.8.0/22','10.999.0.0/22'):
        assert not valid(prefix,bad,defaults(form))
    state=defaults(form);state['hubs']['hub1'].update(deployExpressRouteGateway='true',expressRouteMinScaleUnits='3',expressRouteMaxScaleUnits='2')
    assert not valid(fields['hubs','hub1','expressRouteMaxScaleUnits'],'2',state)
    state=defaults(form);state['policies']['commonPolicyName']='hub-01-policy'
    assert not valid(fields['hubs','hub1','hubName'],'hub-01',state)
    for vpn,er in ((True,False),(False,True),(True,True)):
        state=defaults(form)
        for hub in state['hubs'].values():
            hub.update(deployVpnGateway=str(vpn).lower(),deployExpressRouteGateway=str(er).lower())
        result={k:evaluate(v,state) for k,v in parameters.items()}
        normalize(dict(result,schemaVersion=1,subscriptionId='00000000-0000-0000-0000-000000000000',resourceGroup='rg-portal-test'))
    for mode in ('ParentChildren','Shared','Separate'):
        state=defaults(form);state['network']['hubCount']='4';state['policies']['policyMode']=mode
        state['hubs']['hub2']['inspectionMode']='Disabled'
        state['hubs']['hub3']['inspectionMode']='Internet'
        state['hubs']['hub4']['inspectionMode']='Private'
        result={k:evaluate(v,state) for k,v in parameters.items()}
        normalize(dict(result,schemaVersion=1,subscriptionId='00000000-0000-0000-0000-000000000000',resourceGroup='rg-portal-test'))
    print(f'PASS: {tests} offline configuration cases, mixed secured/unsecured hubs, expression parsing, gateway variants and invalid-input checks.')
    print('Portal rendering and a live portal deployment remain to be verified.')

if __name__=='__main__':
    root=Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root/'scripts/multi-hub-core'))
    import core
    check(json.loads((root/'portal/multi-hub/uiFormDefinition.json').read_text()),
          json.loads((root/'portal/multi-hub/mainTemplate.json').read_text()),core.normalize)
