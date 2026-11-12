# Incident report template

Use this format for every GitHub issue created for a Grubify incident. Fill in every section; write "None observed" instead of leaving a section empty.

## Title

```
[SRE Agent] <symptom> caused by <root cause> (<container app>)
```

Example: `[SRE Agent] HTTP 500s caused by OutOfMemoryException in <Controller> (ca-grubify-api)`

## Labels

Add the labels `sre-agent`, `incident`, and one of `memory-leak`, `payment`, `bug`.

## Body

````markdown
## Summary
<2-3 sentences: what failed, since when, and the root cause in one line.>

## Impact
- **Affected endpoints:** <routes and HTTP status codes>
- **User-facing effect:** <what customers saw>
- **Duration:** <start - end (UTC) or "ongoing">

## Timeline (UTC)
| Time | Event |
|---|---|
| HH:MM | <first anomaly> |
| HH:MM | <alert fired> |
| HH:MM | <peak / restart / mitigation> |

## Evidence
### Metrics
- Requests by status code: <numbers>
- WorkingSetBytes / MemoryPercentage: <trend with numbers>
- RestartCount: <value>
<Chart generated with ExecutePythonCode or the plotting tools when available.>

### Logs
```
<the most relevant log lines and the top of the stack trace>
```

### Queries used
```kusto
<KQL queries you ran>
```

## Root cause
<Technical explanation. Link to the exact source lines, e.g. `GrubifyApi/Controllers/<File>.cs#L<line>`, and explain why the code causes the failure.>

## Remediation
- **Immediate mitigation:** <what was done or recommended>
- **Code fix:** <concrete change, with a short code snippet if helpful>
- **Prevention:** <tests, alerts or limits that would catch this earlier>

## References
- Container app: `<full ARM resource ID>`
- Log Analytics workspace: `<full ARM resource ID>`
- Alert rule: `<alert rule name>`
````
