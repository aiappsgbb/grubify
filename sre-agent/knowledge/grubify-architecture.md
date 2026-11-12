# Grubify Architecture

Grubify is a food delivery demo app on Azure Container Apps. Source code lives in the connected GitHub repository.

## Components

| Component | Container app | Tech | Source path |
|---|---|---|---|
| API | `ca-grubify-api` | .NET 9 ASP.NET Core Web API, port 8080 | `GrubifyApi/` |
| Frontend | `ca-grubify-frontend` | React 19 + TypeScript + MUI, served by nginx on port 80 | `grubify-frontend/` |

Both apps run in the Container Apps environment `cae-grubify` in resource group `rg-grubify-app`.

- Each app has **1 replica (min = max = 1)**, **0.5 vCPU** and **1 GiB memory**. A single replica means any API failure is user-visible immediately.
- The .NET GC heap hard limit defaults to **75% of the container memory limit (~768 MB)**. When the managed heap reaches it, allocations throw `System.OutOfMemoryException` and ASP.NET Core returns **HTTP 500**. If the runtime can't recover, the process aborts and the container restarts.
- State (carts, orders) is held **in memory** in static collections; there is no database.

## API endpoints

| Route | Controller | Purpose |
|---|---|---|
| `GET /api/restaurants` | `RestaurantsController` | Restaurant catalog |
| `GET /api/fooditems` | `FoodItemsController` | Menu items |
| `GET /api/deals` | `DealsController` | Live "Hot Deals" feed. The UI polls it every 3 seconds while the Hot Deals page is open |
| `/api/cart/{userId}` | `CartController` | Shopping cart |
| `POST /api/orders` | `OrdersController` | Places an order and processes payment for the selected payment method |

Payment methods sent by the checkout page: `credit-card`, `digital-wallet`, `cash-on-delivery`, `grubify-pay`.

## Observability

- Container stdout/stderr goes to the Log Analytics workspace `cae-grubify-logs`:
  - `ContainerAppConsoleLogs_CL`: application logs. Columns `ContainerAppName_s`, `RevisionName_s`, `Log_s`.
  - `ContainerAppSystemLogs_CL`: platform events such as restarts, probe failures and OOM kills. Columns `ContainerAppName_s`, `Reason_s`, `Log_s`.
- Azure Monitor platform metrics on the container apps (namespace `microsoft.app/containerapps`): `Requests` (dimensions `statusCodeCategory`, `statusCode`), `WorkingSetBytes`, `MemoryPercentage`, `RestartCount`, `UsageNanoCores`, `ResponseTime`.
- The API writes plain `Console.WriteLine` log lines. Unhandled exceptions are logged by Kestrel as `fail: Microsoft.AspNetCore.Server.Kestrel[13]` followed by the exception type and stack trace, including source file and line numbers.

## Alerting

The metric alert `alert-grubify-api-http-5xx` fires when `ca-grubify-api` returns more than 5 HTTP 5xx responses within 5 minutes. A response plan routes it to the `incident-handler` subagent.
