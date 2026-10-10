import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/multi-hub-core"))
import core

spec = importlib.util.spec_from_file_location(
    "multi_hub_cleanup", ROOT / "scripts/multi-hub-core/remove.py")
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


def settings():
    return json.loads((ROOT / "examples/multi-hub/parentchildren.json").read_text())


class RegressionTests(unittest.TestCase):
    def test_parent_child_region_mismatch_rejected(self):
        c = settings()
        c["hubs"][1]["firewallPolicyLocation"] = "northeurope"
        with self.assertRaisesRegex(ValueError, "same region"):
            core.normalize(c)

    def test_child_region_defaults_to_parent(self):
        c = settings()
        for h in c["hubs"]:
            h.pop("firewallPolicyLocation", None)
        result = core.normalize(c)
        self.assertTrue(all(
            h["firewallPolicyLocation"] == result["commonPolicyLocation"]
            for h in result["hubs"]))

    def test_cleanup_can_read_historical_region_mismatch(self):
        c = settings()
        c["hubs"][1]["firewallPolicyLocation"] = "northeurope"
        result = core.normalize(c, for_cleanup=True)
        self.assertEqual(result["hubs"][1]["firewallPolicyLocation"], "northeurope")

    def workbook_case(self):
        c = core.normalize(settings())
        prefix = ("/subscriptions/" + c["subscriptionId"] +
                  "/resourceGroups/" + c["resourceGroup"] +
                  "/providers/Microsoft.Insights/workbooks/")
        state = {"outputs": {
            "hubResources": {"value": [{"workbookResourceId": prefix + "per-hub"}]},
            "consolidatedWorkbookResourceId": {"value": prefix + "consolidated"}}}
        resource = {"id": prefix + "consolidated", "name": "consolidated",
                    "type": "Microsoft.Insights/workbooks",
                    "tags": core.ownership_tags(c)}
        return c, state, resource

    def test_owned_recorded_consolidated_workbook_allowed(self):
        c, state, resource = self.workbook_case()
        cleanup.allowed_resources(c, state, [resource])

    def test_unrecorded_workbook_refused(self):
        c, state, resource = self.workbook_case()
        resource["id"] += "-unrelated"
        resource["name"] += "-unrelated"
        with self.assertRaisesRegex(ValueError, "removal refused"):
            cleanup.allowed_resources(c, state, [resource])


if __name__ == "__main__":
    unittest.main()
