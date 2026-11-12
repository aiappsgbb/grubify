# Grubify - Food Delivery App

A modern food delivery application built with React TypeScript frontend and .NET backend, designed for deployment to Azure Container Apps using Azure Developer CLI (azd).

## 🍕 Features

- **Modern UI**: Beautiful, responsive design inspired by popular food delivery apps
- **Real Food Content**: Sample restaurants and food items with real images from Unsplash
- **Complete Food Delivery Flow**: Browse restaurants → Add to cart → Checkout → Track orders
- **Azure Container Apps**: Scalable, serverless container hosting
- **Azure Developer CLI**: One-command deployment and management

## 🏗️ Architecture

- **Frontend**: React 18 + TypeScript + Material-UI
- **Backend**: .NET 9 Web API with RESTful endpoints
- **Infrastructure**: Azure Container Apps + Container Registry
- **Deployment**: Azure Developer CLI (azd)
- **Image Builds**: Built in the cloud by Azure Container Registry (ACR Tasks) — no local Docker required

## 🚀 Complete Deployment Guide

This guide deploys Grubify together with an [Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/overview) that investigates production incidents and files GitHub issues. Failures are triggered from the app's own UI, so no extra scripts or redeployments are needed during a demo.

## 📋 Prerequisites

Before deploying Grubify, ensure you have the following tools installed:

### Required Tools
- **[Azure Developer CLI (azd)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)** - Latest version
- **[Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)** - Used to get SRE Agent access tokens
- **Python 3.9+** - Runs the SRE Agent setup hook (standard library only, no packages to install)
- **Azure Subscription** - With Owner, or Contributor + User Access Administrator, permissions (the SRE Agent needs role assignments)
- **GitHub repository** - A fork of this repo with **Issues enabled**, so the SRE Agent can create issues

### ☁️ Cloud Container Builds
Docker is **not** required on your machine. Both services are configured with `docker.remoteBuild: true` in `azure.yaml`, so `azd up` / `azd deploy` uploads each service's source (filtered by its `.dockerignore`) to Azure Container Registry, which builds the image with ACR Tasks and pushes it to the registry.

## 🚀 Quick Start

### 1. Prerequisites Check
Before starting, run our prerequisites check script:

```bash
./scripts/check-prerequisites.sh
```

### 2. Initial Azure Setup

```bash
# Clone your fork of the repository
git clone https://github.com/<your-github-user>/grubify.git
cd grubify

# Login to Azure
azd auth login
az login

# Create an environment and pick a region where Azure SRE Agent is available
azd env new grubify --location eastus2
```

The SRE Agent connects to the GitHub repository of your `origin` remote. To use a different repository, run `azd env set GITHUB_REPO <owner>/<repo>`.

### 3. Deploy Infrastructure, Apps and SRE Agent

```bash
azd up
```

This creates:
- **Resource Group**: `rg-grubify-app`
- **Container Registry**: `crgrubify<unique-suffix>` (registry names must be globally unique)
- **Container Apps Environment**: `cae-grubify`, with the Log Analytics workspace `cae-grubify-logs`
- **API Container App**: `ca-grubify-api`
- **Frontend Container App**: `ca-grubify-frontend`
- **Application Insights**: `appi-grubify`
- **Metric alert**: `alert-grubify-api-http-5xx` (more than 5 HTTP 5xx responses from the API in 5 minutes)
- **Azure SRE Agent**: `sre-grubify-<unique-suffix>`, with Reader, monitoring, Log Analytics and Container Apps Contributor access to the resource group

After provisioning, the `postprovision` hook runs [`scripts/setup_sre_agent.py`](scripts/setup_sre_agent.py), which:
1. Uploads the knowledge base in [`sre-agent/knowledge`](sre-agent/knowledge): the app architecture, an HTTP 5xx runbook and the incident report template.
2. Creates the `incident-handler` subagent defined in [`sre-agent/agents`](sre-agent/agents).
3. Connects Azure Monitor and adds a response plan that sends `alert-grubify-api-http-5xx` to `incident-handler` in autonomous mode.
4. Connects your GitHub repository.

### 4. Authorize GitHub (one time)

The first time, the setup script prints a GitHub OAuth URL. Open it, authorize the Azure SRE Agent, then press Enter. If you ran `azd up` without an interactive terminal, finish the setup after authorizing with:

```bash
python3 scripts/setup_sre_agent.py
```

The script is idempotent and can be re-run at any time.

## 🔥 SRE Scenarios

Both failures are real bugs in the app, triggered from the UI.

| Scenario | How to trigger | What happens |
|---|---|---|
| **Memory leak** | Click **Hot Deals** in the top bar and leave the page open | The page refreshes deals every 3 seconds. Each refresh renders promo banners into a cache that is never evicted, so memory climbs about 47 MB per refresh. After about a minute `/api/deals` returns HTTP 500 (`OutOfMemoryException`), then the whole API starts failing and the container restarts. |
| **Payment failures** | Add items to the cart, check out and choose **Grubify Pay** | Grubify Pay was shipped pointing at a staging payment gateway, so every order returns HTTP 500 (`PAYMENT_ERROR`). Other payment methods keep working. |

Within a few minutes of the 5xx errors, `alert-grubify-api-http-5xx` fires. The SRE Agent then picks up the incident, follows the runbook, finds the faulty code in the repository and creates a GitHub issue with the root cause, evidence and remediation. Follow the investigation at [sre.azure.com](https://sre.azure.com).

To recover from the memory leak, close the Hot Deals page; the container restarts and returns to normal. The agent may also restart the revision as a mitigation.

## 🧹 Clean Up

```bash
azd down --force --purge
```
