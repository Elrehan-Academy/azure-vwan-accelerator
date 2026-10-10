"""Focused offline checks. No Azure resources or credentials required."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/multi-hub-core'))
import core
import deploy
import remove


def example():
    return json.loads((ROOT / 'examples/multi-hub/parentchildren.json').read_text())


class ConfigurationTests(unittest.TestCase):
    def invalid(self, change):
        c = example()
        change(c)
        with self.assertRaises(ValueError):
            core.normalize(c)

    def test_modes_and_hub_counts(self):
        for mode in core.MODES:
            for count in (2, 3, 4):
                with self.subTest(mode=mode, count=count):
                    c = example()
                    c['policyMode'] = mode
                    c['hubs'] = [{'hubName': f'hub-{i}', 'hubLocation': 'westeurope',
                                  'hubAddressPrefix': f'10.250.{i * 4}.0/22'} for i in range(count)]
                    self.assertEqual(len(core.normalize(c)['hubs']), count)

    def test_inspection_and_monitoring_combinations(self):
        for inspection in core.INSPECTIONS:
            for logging, workbook in ((True, True), (True, False), (False, False)):
                with self.subTest(inspection=inspection, logging=logging, workbook=workbook):
                    c = example()
                    c['hubs'][0]['inspectionMode'] = inspection
                    c['enableLogging'], c['enableWorkbook'] = logging, workbook
                    core.normalize(c)
        c = example()
        for h in c['hubs']:
            h['inspectionMode'] = 'Disabled'
        core.normalize(c)

    def test_parameters_do_not_drop_settings(self):
        c = example()
        c.update(logRetentionDays=90, threatIntelMode='Alert', enableDnsProxy=True,
                 commonRuleCollectionGroups=[{'name': 'group-a', 'priority': 150, 'ruleCollections': []}])
        p = core.parameters(c)['parameters']
        for k in core.PARAMETERS:
            self.assertIn(k, p)
        for k in ('logRetentionDays', 'threatIntelMode', 'enableDnsProxy', 'commonRuleCollectionGroups'):
            self.assertEqual(p[k]['value'], c[k])
        b = deploy.bootstrap_parameters(c)['parameters']['coreParameters']['value']
        self.assertEqual(b['hubs'], core.normalize(c)['hubs'])
        self.assertEqual(b['tags']['academyDeploymentId'], core.deployment_id(c))

    def test_overlap(self):
        self.invalid(lambda c: c['hubs'][1].update(hubAddressPrefix=c['hubs'][0]['hubAddressPrefix']))

    def test_duplicate_hub_case_insensitive(self):
        self.invalid(lambda c: c['hubs'][1].update(hubName='HUB-WEST'))

    def test_child_parent_name_conflict(self):
        self.invalid(lambda c: c['hubs'][0].update(firewallPolicyName=c['commonPolicyName']))

    def test_duplicate_firewall(self):
        self.invalid(lambda c: c['hubs'][1].update(firewallName=c['hubs'][0]['firewallName']))

    def test_duplicate_policy(self):
        self.invalid(lambda c: c['hubs'][1].update(firewallPolicyName=c['hubs'][0]['firewallPolicyName']))

    def test_invalid_zone(self):
        self.invalid(lambda c: c['hubs'][0].update(firewallZones=[1, 1]))
        self.invalid(lambda c: c['hubs'][0].update(firewallZones=[True]))

    def test_insufficient_secured_prefix(self):
        self.invalid(lambda c: c['hubs'][0].update(hubAddressPrefix='10.250.0.0/24'))

    def test_non_private_prefix(self):
        self.invalid(lambda c: c['hubs'][0].update(hubAddressPrefix='8.8.8.0/22'))

    def test_invalid_modes(self):
        self.invalid(lambda c: c.update(policyMode='Sharedish'))
        self.invalid(lambda c: c.update(firewallTier='Basic'))

    def test_boolean_is_not_integer(self):
        self.invalid(lambda c: c.update(logRetentionDays=True))
        self.invalid(lambda c: c.update(enableLogging='true'))

    def test_unknown_field_rejected(self):
        self.invalid(lambda c: c.update(logRetentionDay=60))
        self.invalid(lambda c: c['hubs'][0].update(firewallZone=[1]))

    def test_shared_cannot_drop_hub_rules(self):
        def change(c):
            c['policyMode'] = 'Shared'
            c['hubs'][0]['ruleCollectionGroups'] = [{'name': 'rules', 'priority': 100, 'ruleCollections': []}]
        self.invalid(change)

    def test_separate_cannot_drop_parent_rules(self):
        self.invalid(lambda c: c.update(policyMode='Separate', commonRuleCollectionGroups=[{'name': 'rules', 'priority': 100, 'ruleCollections': []}]))

    def test_workbook_requires_logging(self):
        self.invalid(lambda c: c.update(enableLogging=False, enableWorkbook=True))

    def test_reserved_tags(self):
        self.invalid(lambda c: c.update(tags={'AcademyDeploymentId': 'other'}))
        self.invalid(lambda c: c['hubs'][0].update(tags={'academyPackage': 'other'}))

    def test_gateway_bounds(self):
        self.invalid(lambda c: c['hubs'][0].update(expressRouteParameters={
            'deployExpressRouteGateway': True, 'expressRouteGatewayName': 'er',
            'autoScaleConfigurationBoundsMin': 5, 'autoScaleConfigurationBoundsMax': 2}))

    def test_gateway_variants(self):
        for vpn in (False, True):
            for er in (False, True):
                c = example()
                c['hubs'][0]['s2sVpnParameters'] = {'deployS2SVpnGateway': vpn, 'vpnGatewayName': 'vpn', 'vpnGatewayScaleUnit': 1}
                c['hubs'][0]['expressRouteParameters'] = {'deployExpressRouteGateway': er, 'expressRouteGatewayName': 'er', 'autoScaleConfigurationBoundsMin': 1, 'autoScaleConfigurationBoundsMax': 2}
                core.normalize(c)


class WorkflowTests(unittest.TestCase):
    def test_local_preview_does_not_call_azure(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'c.json'
            p.write_text(json.dumps(example()))
            with patch.object(sys, 'argv', ['deploy.py', '--config', str(p)]), patch.object(deploy, 'az') as az:
                deploy.main()
                az.assert_not_called()

    def test_what_if_error_propagates(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'c.json'
            p.write_text(json.dumps(example()))
            with patch.object(sys, 'argv', ['deploy.py', '--config', str(p), '--what-if']), \
                    patch.object(deploy, 'verify_subscription'), patch.object(deploy, 'group_gate'), \
                    patch.object(deploy, 'state_path', return_value=Path(td) / 'state.json'), \
                    patch.object(deploy, 'az', side_effect=RuntimeError('what-if failed')):
                with self.assertRaisesRegex(RuntimeError, 'what-if failed'):
                    deploy.main()

    def test_unrelated_rg_refused(self):
        c = example()
        with patch.object(deploy, 'az', side_effect=[True, {'location': 'westeurope', 'tags': {}}, [{'id': 'unrelated'}]]):
            with self.assertRaises(ValueError):
                deploy.group_gate(c, None)

    def test_empty_rg_needs_opt_in(self):
        c = example()
        responses = [True, {'location': 'westeurope', 'tags': {}}, []]
        with patch.object(deploy, 'az', side_effect=responses):
            with self.assertRaises(ValueError):
                deploy.group_gate(c, None)
        with patch.object(deploy, 'az', side_effect=responses):
            deploy.group_gate(c, None, allow_empty=True)

    def test_tagged_rg_without_state_refused(self):
        c = example()
        with patch.object(deploy, 'az', side_effect=[True, {'location': 'westeurope', 'tags': core.ownership_tags(c)}, []]):
            with self.assertRaises(ValueError):
                deploy.group_gate(c, None)

    def test_remove_refuses_unrelated_vm(self):
        c = core.normalize(example())
        resource = {'id': '/unrelated/vm', 'type': 'Microsoft.Compute/virtualMachines', 'name': 'vm', 'tags': core.ownership_tags(c)}
        with self.assertRaises(ValueError):
            remove.allowed_resources(c, {}, [resource])

    def test_remove_refuses_unowned_core(self):
        c = core.normalize(example())
        resource = {'id': '/wan', 'type': 'Microsoft.Network/virtualWans', 'name': c['virtualWanName'], 'tags': {}}
        with self.assertRaises(ValueError):
            remove.allowed_resources(c, {}, [resource])

    def test_remove_accepts_owned_core(self):
        c = core.normalize(example())
        resource = {'id': '/wan', 'type': 'Microsoft.Network/virtualWans', 'name': c['virtualWanName'], 'tags': core.ownership_tags(c)}
        remove.allowed_resources(c, {}, [resource])

    def test_remove_workbook_identity(self):
        c = core.normalize(example())
        state = {'outputs': {'hubResources': {'value': [{'workbookResourceId': '/expected-workbook'}]}}}
        resource = {'id': '/other-workbook', 'type': 'Microsoft.Insights/workbooks', 'name': 'other', 'tags': core.ownership_tags(c)}
        with self.assertRaises(ValueError):
            remove.allowed_resources(c, state, [resource])

    def test_azure_failure_raises(self):
        with patch.object(core.shutil, 'which', return_value='/az'), patch.object(core.subprocess, 'run',
                return_value=subprocess.CompletedProcess([], 1, '', 'denied')):
            with self.assertRaisesRegex(RuntimeError, 'denied'):
                core.az(['group', 'exists'])


if __name__ == '__main__':
    unittest.main()
