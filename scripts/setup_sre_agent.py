#!/usr/bin/env python3
"""Configure the Azure SRE Agent for Grubify after `azd provision`.

Runs as an azd `postprovision` hook and can be re-run at any time; every step is idempotent.

Steps:
  1. Upload the knowledge base in sre-agent/knowledge.
  2. Create the `incident-handler` subagent from sre-agent/agents.
  3. Enable Azure Monitor as the incident platform and route the HTTP 5xx alert to the subagent.
  4. Connect GitHub (one-time browser OAuth) and the Grubify repository.

Uses only the Python standard library plus the Azure CLI (`az login`) for access tokens.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "sre-agent" / "knowledge"
AGENTS_DIR = ROOT / "sre-agent" / "agents"

ARM_ENDPOINT = "https://management.azure.com"
SRE_RESOURCE = "https://azuresre.dev"
AGENT_API_VERSION = "2025-05-01-preview"
SUBAGENT_NAME = "incident-handler"
RESPONSE_PLAN_NAME = "grubify-http-errors"
REPO_PLACEHOLDER = "GITHUB_REPO_PLACEHOLDER"
TRANSIENT_STATUSES = {401, 403, 404, 405, 408, 409, 429, 500, 502, 503, 504}


class SetupError(Exception):
    pass


def log(message: str = "") -> None:
    print(message, flush=True)


def which(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SetupError(f"'{name}' was not found on PATH.")
    return path


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SetupError(f"{' '.join(cmd[:4])} ... failed: {result.stderr.strip()}")
    return result.stdout.strip()


def load_settings() -> dict[str, str]:
    """Read azd environment values; real environment variables (set by azd for hooks) win."""
    values: dict[str, str] = {}
    azd = shutil.which("azd")
    if azd:
        result = subprocess.run([azd, "env", "get-values"], capture_output=True, text=True, cwd=ROOT)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)="?(.*?)"?$', line.strip())
                if match:
                    values[match.group(1)] = match.group(2)
    for key in list(values) + [
        "SRE_AGENT_ENDPOINT",
        "SRE_AGENT_ID",
        "SRE_AGENT_NAME",
        "HTTP_5XX_ALERT_NAME",
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_RESOURCE_GROUP",
        "GITHUB_REPO",
    ]:
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def detect_github_repo() -> str:
    try:
        url = run([which("git"), "-C", str(ROOT), "remote", "get-url", "origin"])
    except SetupError:
        return ""
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    return f"{match.group(1)}/{match.group(2)}" if match else ""


class Client:
    def __init__(self, endpoint: str, subscription: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.subscription = subscription
        self.az = which("az")
        self._tokens: dict[str, tuple[str, float]] = {}

    def token(self, resource: str, refresh: bool = False) -> str:
        cached = self._tokens.get(resource)
        if cached and not refresh and time.time() - cached[1] < 1800:
            return cached[0]
        cmd = [self.az, "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"]
        if self.subscription:
            cmd += ["--subscription", self.subscription]
        value = run(cmd)
        if not value:
            raise SetupError(f"Could not get an access token for {resource}. Run 'az login'.")
        self._tokens[resource] = (value, time.time())
        return value

    def request(self, method: str, url: str, resource: str, body: object | None = None) -> tuple[int, object]:
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(2):
            req = urllib.request.Request(
                url,
                data=data,
                method=method,
                headers={
                    "Authorization": f"Bearer {self.token(resource, refresh=attempt > 0)}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return resp.status, _parse(resp.read())
            except urllib.error.HTTPError as err:
                if err.code == 401 and attempt == 0:
                    continue
                return err.code, _parse(err.read())
            except urllib.error.URLError as err:
                return 0, str(err.reason)
        return 401, None

    def agent(self, method: str, path: str, body: object | None = None) -> tuple[int, object]:
        return self.request(method, f"{self.endpoint}{path}", SRE_RESOURCE, body)

    def agent_with_retry(
        self,
        method: str,
        path: str,
        body: object | None = None,
        attempts: int = 5,
        delay: int = 15,
        retry_codes: tuple[str, ...] = (),
    ) -> tuple[int, object]:
        status, payload = 0, None
        for attempt in range(1, attempts + 1):
            status, payload = self.agent(method, path, body)
            if 200 <= status < 300:
                return status, payload
            pending = any(code in json.dumps(payload) for code in retry_codes)
            if status not in TRANSIENT_STATUSES | {0} and not pending:
                return status, payload
            if attempt < attempts:
                log(f"   ...HTTP {status}, retrying in {delay}s ({attempt}/{attempts})")
                time.sleep(delay)
        return status, payload

    def arm(self, method: str, resource_id: str, body: object | None = None) -> tuple[int, object]:
        url = f"{ARM_ENDPOINT}{resource_id}?api-version={AGENT_API_VERSION}"
        return self.request(method, url, ARM_ENDPOINT, body)


def _parse(raw: bytes) -> object:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode(errors="replace")


def _require_ok(status: int, payload: object, what: str) -> None:
    if not 200 <= status < 300:
        detail = json.dumps(payload)[:500] if not isinstance(payload, str) else payload[:500]
        raise SetupError(f"{what} failed with HTTP {status}: {detail}")


def wait_for_agent(client: Client, timeout: int = 600) -> None:
    """Wait for the data plane to accept our token; new role assignments can take minutes to apply."""
    log("⏳ Waiting for the SRE Agent data plane...")
    deadline = time.time() + timeout
    while True:
        status, payload = client.agent("GET", "/api/v2/extendedAgent/agents")
        if status == 200:
            log("   ✅ Ready")
            return
        if time.time() > deadline:
            _require_ok(status, payload, "SRE Agent data plane check")
        log(f"   ...HTTP {status or payload}, retrying in 20s")
        time.sleep(20)


def connector_name(file_name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", file_name.lower())).strip("-")


def upload_knowledge(client: Client) -> None:
    log("📚 Uploading knowledge base...")
    files = sorted(KNOWLEDGE_DIR.glob("*.md"))
    if not files:
        raise SetupError(f"No knowledge files found in {KNOWLEDGE_DIR}")
    for path in files:
        name = connector_name(path.name)
        body = {
            "name": name,
            "type": "KnowledgeItem",
            "tags": [],
            "properties": {
                "dataConnectorType": "KnowledgeFile",
                "dataSource": name,
                "extendedProperties": {
                    "displayName": path.name,
                    "fileName": path.name,
                    "fileContent": base64.b64encode(path.read_bytes()).decode(),
                    "contentType": "text/markdown",
                },
            },
        }
        status, payload = client.agent_with_retry("PUT", f"/api/v2/extendedAgent/connectors/{name}", body)
        _require_ok(status, payload, f"Knowledge upload {path.name}")
        log(f"   ✅ {path.name}")


def create_subagent(client: Client, github_repo: str) -> None:
    log(f"🤖 Creating subagent '{SUBAGENT_NAME}'...")
    spec = json.loads((AGENTS_DIR / f"{SUBAGENT_NAME}.json").read_text())
    instructions = (AGENTS_DIR / spec["instructionsFile"]).read_text()
    instructions = instructions.replace(REPO_PLACEHOLDER, github_repo or "the connected GitHub repository")
    body = {
        "name": spec["name"],
        "type": "ExtendedAgent",
        "tags": [],
        "owner": "",
        "properties": {
            "instructions": instructions,
            "handoffDescription": spec["handoffDescription"],
            "handoffs": [],
            "tools": spec["tools"],
            "mcpTools": [],
            "allowParallelToolCalls": True,
            "enableSkills": True,
        },
    }
    status, payload = client.agent_with_retry("PUT", f"/api/v2/extendedAgent/agents/{spec['name']}", body)
    _require_ok(status, payload, f"Subagent {spec['name']}")
    log("   ✅ Created")


def wait_for_agent_update(client: Client, agent_id: str, timeout: int = 900) -> None:
    """Configuration changes are applied asynchronously; the data plane rejects dependent calls until they finish."""
    deadline = time.time() + timeout
    while True:
        status, agent = client.arm("GET", agent_id)
        _require_ok(status, agent, "Reading the SRE Agent resource")
        state = (agent.get("properties") or {}).get("provisioningState", "")
        if state in ("Succeeded", "Failed", "Canceled"):
            if state != "Succeeded":
                raise SetupError(f"SRE Agent update finished with state '{state}'")
            return
        if time.time() > deadline:
            raise SetupError(f"SRE Agent update still '{state}' after {timeout}s. Re-run this script later.")
        log(f"   ...agent update {state or 'pending'}, checking again in 20s")
        time.sleep(20)


def configure_incident_response(client: Client, agent_id: str, alert_name: str) -> None:
    log("🚨 Connecting Azure Monitor alerts...")
    status, agent = client.arm("GET", agent_id)
    _require_ok(status, agent, "Reading the SRE Agent resource")
    incident_cfg = (agent.get("properties") or {}).get("incidentManagementConfiguration") or {}
    if incident_cfg.get("type") == "AzMonitor":
        log("   ✅ Azure Monitor already enabled")
    else:
        body = {
            "properties": {
                "incidentManagementConfiguration": {"type": "AzMonitor", "connectionName": "azmonitor"},
                "experimentalSettings": {
                    "EnableWorkspaceTools": True,
                    "EnableDevOpsTools": True,
                    "EnablePythonTools": True,
                },
            }
        }
        status, payload = client.arm("PATCH", agent_id, body)
        _require_ok(status, payload, "Enabling Azure Monitor incident management")
        log("   ✅ Azure Monitor enabled")
    wait_for_agent_update(client, agent_id)

    body = {
        "name": RESPONSE_PLAN_NAME,
        "type": "IncidentFilter",
        "tags": [],
        "properties": {
            "incidentPlatform": "AzMonitor",
            "priorities": ["Sev0", "Sev1", "Sev2", "Sev3", "Sev4"],
            "titleContains": alert_name,
            "titleContainsAll": [],
            "titleContainsAny": [],
            "titleNotContains": [],
            "handlingAgent": SUBAGENT_NAME,
            "agentMode": "Autonomous",
            "maxAutomatedInvestigationAttempts": 3,
            # Both demo scenarios fire the same alert rule; merging would fold a
            # payment-failure alert into an earlier memory-leak incident unseen.
            "mergeEnabled": False,
            "mergeWindowHours": 3,
            "isEnabled": True,
        },
    }
    status, payload = client.agent_with_retry(
        "PUT",
        f"/api/v2/extendedAgent/incidentFilters/{RESPONSE_PLAN_NAME}",
        body,
        attempts=20,
        retry_codes=("IncidentPlatformConfigurationPending",),
    )
    _require_ok(status, payload, "Response plan")
    log(f"   ✅ Response plan '{RESPONSE_PLAN_NAME}': '{alert_name}' -> {SUBAGENT_NAME} (autonomous)")


def github_connected(client: Client) -> bool:
    status, payload = client.agent("GET", "/api/v2/github/domains")
    return status == 200 and isinstance(payload, dict) and bool(payload.get("values"))


def connect_github(client: Client, github_repo: str, wait: bool, timeout: int) -> bool:
    log("🔗 Connecting GitHub...")
    if not github_connected(client):
        status, payload = client.agent_with_retry("GET", "/api/v2/github/oauth/config")
        _require_ok(status, payload, "Reading the GitHub OAuth URL")
        config = payload if isinstance(payload, dict) else {}
        oauth_url = config.get("oAuthUrl") or config.get("OAuthUrl")
        if not oauth_url:
            raise SetupError("The SRE Agent did not return a GitHub OAuth URL.")
        log("")
        log("   Authorize the SRE Agent to access GitHub by opening this URL (one-time step):")
        log(f"   {oauth_url}")
        log("")
        interactive = sys.stdin.isatty() and not wait
        if interactive:
            input("   Press Enter after you've authorized GitHub access...")
        elif not wait:
            log("   ⚠️  GitHub isn't connected yet. After authorizing, finish the setup with:")
            log("      python3 scripts/setup_sre_agent.py")
            return False
        deadline = time.time() + (60 if interactive else timeout)
        while not github_connected(client):
            if time.time() > deadline:
                log("   ⚠️  GitHub authorization wasn't detected. Re-run this script after authorizing.")
                return False
            time.sleep(10)
    log("   ✅ GitHub authorized")

    repo_name = github_repo.split("/")[-1]
    body = {
        "name": repo_name,
        "type": "CodeRepo",
        "properties": {
            "url": f"https://github.com/{github_repo}",
            "type": "GitHub",
            "description": "Grubify food delivery app source code (API in GrubifyApi/, frontend in grubify-frontend/)",
        },
    }
    status, payload = client.agent_with_retry("PUT", f"/api/v2/repos/{repo_name}", body)
    _require_ok(status, payload, f"Connecting repository {github_repo}")
    log(f"   ✅ Repository {github_repo} connected")
    return True


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wait-for-github", action="store_true", help="poll until GitHub OAuth is authorized")
    parser.add_argument("--github-timeout", type=int, default=900, help="seconds to wait with --wait-for-github")
    args = parser.parse_args()

    settings = load_settings()
    endpoint = settings.get("SRE_AGENT_ENDPOINT", "")
    agent_id = settings.get("SRE_AGENT_ID", "")
    alert_name = settings.get("HTTP_5XX_ALERT_NAME", "alert-grubify-api-http-5xx")
    github_repo = settings.get("GITHUB_REPO") or detect_github_repo()
    if not endpoint or not agent_id:
        log("❌ SRE_AGENT_ENDPOINT / SRE_AGENT_ID are not set. Run 'azd provision' first.")
        return 1

    log("")
    log("=============================================")
    log("  Grubify SRE Agent setup")
    log("=============================================")
    log(f"  Agent:      {settings.get('SRE_AGENT_NAME', agent_id.rsplit('/', 1)[-1])}")
    log(f"  Endpoint:   {endpoint}")
    log(f"  Alert:      {alert_name}")
    log(f"  Repository: {github_repo or '(not detected - set GITHUB_REPO=owner/repo)'}")
    log("")

    client = Client(endpoint, settings.get("AZURE_SUBSCRIPTION_ID", ""))
    try:
        wait_for_agent(client)
        upload_knowledge(client)
        create_subagent(client, github_repo)
        configure_incident_response(client, agent_id, alert_name)
        github_ready = bool(github_repo) and connect_github(client, github_repo, args.wait_for_github, args.github_timeout)
    except SetupError as err:
        log(f"❌ {err}")
        return 1

    log("")
    log("=============================================")
    log("  ✅ SRE Agent configured" if github_ready else "  ⚠️  SRE Agent configured, GitHub pending")
    log("=============================================")
    log("  Portal: https://sre.azure.com")
    log("  Demo:   open the Grubify UI and click 'Hot Deals' (memory leak),")
    log("          or check out with 'Grubify Pay' (payment failures).")
    log("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
