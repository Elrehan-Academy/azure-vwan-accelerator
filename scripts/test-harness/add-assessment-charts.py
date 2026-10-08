import json
from pathlib import Path

path = Path("modules/observability/firewall-workbook.json")
data = json.loads(path.read_text())
catalog = json.loads(Path("modules/observability/assessment-checks.json").read_text())

if any(i.get("name") == "academy-report-header" for i in data["items"]):
    raise SystemExit("Report charts already exist.")

visibility = {
    "parameterName": "selectedTab",
    "comparison": "isEqualTo",
    "value": "AcademyAssessment",
}

def table(name, title, query, visual="table"):
    return {
        "type": 3,
        "name": name,
        "conditionalVisibility": visibility,
        "content": {
            "version": "KqlItem/1.0",
            "title": title,
            "query": query,
            "size": 0,
            "queryType": 0,
            "resourceType": "microsoft.operationalinsights/workspaces",
            "crossComponentResources": ["{Workspaces}"],
            "visualization": visual,
        },
    }

items = []
print("Report builder loaded.")

parameters = next(
    i["content"]["parameters"]
    for i in data["items"]
    if i.get("type") == 9 and any(
        p.get("name") == "Workspaces"
        for p in i.get("content", {}).get("parameters", [])
    )
)

snapshot = {
    "generatedUtc": "",
    "firewallId": "__FIREWALL_RESOURCE_ID__",
    "checks": [
        {
            **check,
            "status": "Not assessed",
            "observed": "No assessment supplied.",
            "recommendation": check["requiredEvidence"],
        }
        for check in catalog["checks"]
    ],
    "ruleFindings": [],
}

parameters.append({
    "id": "academy-assessment-snapshot",
    "version": "KqlParameterItem/1.0",
    "name": "AssessmentSnapshot",
    "type": 1,
    "isHiddenWhenLocked": True,
    "value": json.dumps(snapshot),
})

base = """
let report = dynamic({AssessmentSnapshot});
print Checks=report.checks, Firewall=tostring(report.firewallId),
      AssessedAt=tostring(report.generatedUtc)
| where Firewall in~ ({Resource})
| mv-expand Check=Checks
| extend Framework=tostring(Check.framework), Status=tostring(Check.status),
         CheckId=tostring(Check.id), Title=tostring(Check["title"]),
         Reference=tostring(Check.reference), Observed=tostring(Check.observed),
         Recommendation=tostring(Check.recommendation)
"""

items.append({
    "type": 1,
    "name": "academy-report-header",
    "conditionalVisibility": visibility,
    "content": {"json": (
        "## NIST assessment report\n"
        "**Timestamped snapshot:** rerun the assessment after configuration changes.\n\n"
        "Read assessed pass rate together with coverage. Review required and "
        "Not assessed never count as Pass. These are project checks mapped to "
        "selected framework topics, not a compliance certification."
    )},
})

for framework in ("NIST",):
    filtered = base + f'\n| where Framework == "{framework}"\n'

    summary = filtered + """
| summarize Total=count(), Passed=countif(Status=="Pass"),
            Failed=countif(Status=="Fail"),
            Review=countif(Status=="Review required"),
            NotAssessed=countif(Status=="Not assessed"),
            EvaluatedAt=take_any(AssessedAt)
| extend Assessed=Passed+Failed
| extend PassRatePercent=iff(Assessed>0,
             round(100.0*Passed/Assessed,1), real(null)),
         CoveragePercent=iff(Total>0,
             round(100.0*Assessed/Total,1), real(null))
| project EvaluatedAt, Total, Passed, Failed, Review,
          NotAssessed, PassRatePercent, CoveragePercent
"""
    items.append(table(
        f"academy-report-{framework}-summary",
        f"{framework} — assessment summary", summary,
    ))
    items.append(table(
        f"academy-report-{framework}-chart",
        f"{framework} — check status",
        filtered + "| summarize Checks=count() by Status",
        "piechart",
    ))
    items.append(table(
        f"academy-report-{framework}-details",
        f"{framework} — evidence and recommendations",
        filtered + """
| project CheckId, Title, Status, Reference, Observed, Recommendation
| order by CheckId asc
""",
    ))

items.append(table(
    "academy-report-rule-findings",
    "Policy rules — scope and findings",
    """
let report = dynamic({AssessmentSnapshot});
print Findings=report.ruleFindings, Firewall=tostring(report.firewallId)
| where Firewall in~ ({Resource})
| mv-expand Finding=Findings
| project Rule=tostring(Finding.rule), Group=tostring(Finding.group),
          Action=tostring(Finding.action), Sources=tostring(Finding.sources),
          Destinations=tostring(Finding.destinations),
          Ports=tostring(Finding.ports), Findings=tostring(Finding.findings)
""",
))

position = next(
    index for index, item in enumerate(data["items"])
    if item.get("name") == "academy-assessment-intro"
) + 1
data["items"][position:position] = items
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
print("PASS: NIST charts, summaries and findings added to source.")
print("New deployments default to Not assessed until a report is supplied.")
print("Live workbook unchanged.")
