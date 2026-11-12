# Runbook: Grubify API HTTP 5xx errors

Use this runbook when `alert-grubify-api-http-5xx` fires on `ca-grubify-api`. Collect evidence for every step before you conclude a root cause.

## 1. Scope the impact

Query the `Requests` metric for `ca-grubify-api` over the last hour, split by `statusCode`. Record:

- When the 5xx errors started.
- The peak 5xx count per minute.
- Whether 2xx traffic continued or dropped as well. A drop in 2xx means the whole API is down, not a single endpoint.

## 2. Find the failing requests in the application logs

Run this against the environment's Log Analytics workspace:

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(1h)
| where ContainerAppName_s == "ca-grubify-api"
| where Log_s has_any ("Exception", "fail:", "error", "failed", "PAYMENT_ERROR")
| project TimeGenerated, RevisionName_s, Log_s
| order by TimeGenerated desc
| take 200
```

Group the errors by exception type or message to tell apart one failure mode from several. For each failure mode, also pull the log lines just **before** the first error, because they often show the state leading up to the failure:

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(1h)
| where ContainerAppName_s == "ca-grubify-api"
| project TimeGenerated, Log_s
| order by TimeGenerated asc
```

## 3. Check memory and restarts

Memory problems in .NET on a 1 GiB container usually look like this:

1. `WorkingSetBytes` / `MemoryPercentage` climb steadily instead of plateauing.
2. Requests that allocate memory start failing with `System.OutOfMemoryException` (HTTP 500).
3. Other endpoints may start failing too, and the process can abort ("Out of memory.").
4. `RestartCount` increments and memory drops back to baseline, then climbs again if the trigger continues.

Check `ContainerAppSystemLogs_CL` for restarts and terminations:

```kusto
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(1h)
| where ContainerAppName_s == "ca-grubify-api"
| project TimeGenerated, Reason_s, Log_s
| order by TimeGenerated desc
```

If memory grows steadily, identify **which request path drives the growth**:

- Correlate the timing of the growth with the endpoints being called and the log lines they emit.
- Look for log lines that report growing counts or sizes.

## 4. Check payment failures

Order placement returns HTTP 500 with `code: PAYMENT_ERROR` when payment processing fails.

- Search the logs for `Payment processing failed`.
- Determine whether the failures affect **all payment methods** or **one specific payment method**.
- Capture the payment gateway URL in the log lines and compare it with the gateway used by successful payments. A non-production gateway (for example a `staging` or `internal` host) in production is a configuration or code defect.

## 5. Correlate with source code

Use the connected GitHub repository to find the code path behind each failure mode. Stack traces include file names and line numbers under `GrubifyApi/Controllers/`.

- **Memory growth:** look for `static` collections (lists, dictionaries, caches) that are only ever added to. Also look for cache keys that never repeat (timestamps, GUIDs, ticks), which make a cache unbounded.
- **Payment failures:** inspect `OrdersController` to see how each payment method selects its gateway and why it fails.

Cite the exact file path and line numbers in the issue.

## 6. Mitigate

- Don't change scale settings, images or configuration.
- For an unbounded memory leak you may restart the active revision **once**, after collecting evidence, to restore service. The leak will return as long as the triggering feature is in use, so the code fix is required.
- Payment failures can't be mitigated by a restart; recommend the code fix.

## 7. Report

1. Search existing open issues in the repository for the same root cause. If one exists, add a comment with the new evidence instead of opening a duplicate.
2. Otherwise create **one GitHub issue per distinct root cause** using the "Incident report template" knowledge document.
