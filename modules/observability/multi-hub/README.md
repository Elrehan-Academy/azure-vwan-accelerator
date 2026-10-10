# Multi-Hub observability

These assets are dedicated to Multi-Hub deployment. The layout is based on the
approved Azure Firewall workbook. Single-Hub uses the original files in the
parent folder. Shared upstream source and license information remains in
`../SOURCE.md` and `../UPSTREAM-LICENSE`.

`main.bicep` selects one firewall; `consolidated.bicep` selects all deployed
firewalls. The consolidated view does not publish an aggregate assessment.

Run `python3 scripts/multi-hub-core/check-workbooks.py` before rebuilding.
