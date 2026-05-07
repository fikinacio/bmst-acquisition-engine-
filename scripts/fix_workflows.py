"""
Corrige os workflows BMST via API n8n.
Uso: python scripts/fix_workflows.py
"""

import json, os, sys, re, requests
from dotenv import load_dotenv
load_dotenv()

# Suprimir warnings SSL
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5ZDExZDRmZC0xZjVmLTRiYTUtOWUxMi03YWQ4YWY3MDcyNWIiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiYjU3MTRkYTktNzljOC00OWI3LWE2MWMtY2I2Nzc2MDA1NDg3IiwiaWF0IjoxNzc3NzEzOTUzfQ.YhIHnghZqW6ktd7qoVJkSxWg1_0tWPBD3VA90BCNwIc"
N8N_BASE  = "https://www.n8n.biscaplus.com"
HEADERS   = {"X-N8N-API-KEY": TOKEN, "Content-Type": "application/json"}

FASTAPI_URL       = "https://api.biscaplus.com"
ERROR_HANDLER_URL = f"{N8N_BASE}/webhook/error-handler"
AIRTABLE_BASE_ID  = "appFWSWvTMzFYJCAv"
AIRTABLE_TABLE_COMPANIES    = "tblpED6NVZ8gViriH"
AIRTABLE_TABLE_INTERACTIONS = "tbljk7jdoBCgVeapM"
EVOLUTION_URL     = "https://evolution.biscaplus.com"
EVOLUTION_INST    = "bmst"

WF_IDS = {
    "WF03": "NDsuDNsYSypcumPN",
    "WF05": "PdBO2lsXukNI0CFB",
    "WF06": "2ZATYmfxSeYPoHNQ",
}

# Apenas estes campos sao aceites pelo PUT do n8n
PUT_FIELDS = {"name", "nodes", "connections", "settings", "staticData", "pinData"}


def get_wf(wf_id):
    r = requests.get(f"{N8N_BASE}/api/v1/workflows/{wf_id}", headers=HEADERS, verify=False)
    r.raise_for_status()
    return r.json()


ALLOWED_SETTINGS = {"executionOrder", "saveManualExecutions", "callerPolicy",
                    "errorWorkflow", "timezone", "saveExecutionProgress", "saveDataSuccessExecution",
                    "saveDataErrorExecution"}

def put_wf(wf_id, wf):
    payload = {k: v for k, v in wf.items() if k in PUT_FIELDS}
    if "settings" in payload:
        payload["settings"] = {k: v for k, v in payload["settings"].items()
                                if k in ALLOWED_SETTINGS}
    r = requests.put(f"{N8N_BASE}/api/v1/workflows/{wf_id}", headers=HEADERS,
                     json=payload, verify=False)
    if not r.ok:
        print(f"  ERRO PUT {r.status_code}: {r.text[:400]}")
        r.raise_for_status()
    return r.json()


def fix_expression(val):
    """Substitui $env.VAR por valores reais dentro de expressoes n8n."""
    if not isinstance(val, str):
        return val
    # Padrao: ={{ $env.N8N_WEBHOOK_BASE_URL + '/webhook/error-handler' }}
    val = re.sub(
        r"=\{\{.*?\$env\.N8N_WEBHOOK_BASE_URL.*?'(/[^']*)'.*?\}\}",
        lambda m: ERROR_HANDLER_URL + m.group(1) if "/webhook/error-handler" in m.group(0) else val,
        val,
    )
    # Substituicoes simples
    subs = {
        "={{ $env.N8N_WEBHOOK_BASE_URL + '/webhook/error-handler' }}": ERROR_HANDLER_URL,
        "={{ $env.FASTAPI_BASE_URL }}/qualify": f"{FASTAPI_URL}/qualify",
        "={{ $env.FASTAPI_BASE_URL }}/run-prospecting": f"{FASTAPI_URL}/run-prospecting",
        "$env.FASTAPI_BASE_URL": FASTAPI_URL,
        "$env.N8N_WEBHOOK_BASE_URL": N8N_BASE,
        "$env.AIRTABLE_BASE_ID": AIRTABLE_BASE_ID,
        "$env.EVOLUTION_API_URL": EVOLUTION_URL,
        "$env.EVOLUTION_INSTANCE": EVOLUTION_INST,
        "=http://localhost:8000": FASTAPI_URL,
        "http://localhost:8000": FASTAPI_URL,
    }
    for old, new in subs.items():
        val = val.replace(old, new)
    return val


def fix_params_recursive(obj):
    """Percorre recursivamente e corrige strings com $env ou localhost."""
    if isinstance(obj, str):
        return fix_expression(obj)
    if isinstance(obj, dict):
        return {k: fix_params_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fix_params_recursive(i) for i in obj]
    return obj


def fix_airtable_lookup(node, filter_formula):
    """Substitui 'search' sem filtro por 'list' com filterByFormula."""
    p = node.get("parameters", {})
    if p.get("operation") != "search":
        return
    node["parameters"] = {
        "operation": "list",
        "base":  {"__rl": True, "value": AIRTABLE_BASE_ID, "mode": "id"},
        "table": {"__rl": True, "value": AIRTABLE_TABLE_COMPANIES, "mode": "id"},
        "filterByFormula": filter_formula,
        "options": {},
    }


def fix_wf03(wf):
    for node in wf["nodes"]:
        name = node["name"]
        if name == "Airtable — Lookup Company":
            fix_airtable_lookup(
                node,
                "={{ \"{whatsapp_number}='\" + $json.whatsapp_number + \"'\" }}"
            )
    wf = fix_params_recursive(wf)
    return wf


def fix_wf05(wf):
    wf = fix_params_recursive(wf)
    return wf


def fix_wf06(wf):
    for node in wf["nodes"]:
        name = node["name"]
        # Nurture lookup por state=nurture — ja tem filterByFormula provavelmente
        if name == "Airtable — Get Nurture Companies":
            p = node.get("parameters", {})
            if p.get("operation") == "search":
                node["parameters"] = {
                    "operation": "list",
                    "base":  {"__rl": True, "value": AIRTABLE_BASE_ID, "mode": "id"},
                    "table": {"__rl": True, "value": AIRTABLE_TABLE_COMPANIES, "mode": "id"},
                    "filterByFormula": "{state}='nurture'",
                    "options": {},
                }
    wf = fix_params_recursive(wf)
    return wf


FIXERS = {"WF03": fix_wf03, "WF05": fix_wf05, "WF06": fix_wf06}


def main():
    ok = 0
    for name, wf_id in WF_IDS.items():
        print(f"\n=== {name} ({wf_id}) ===")
        try:
            wf = get_wf(wf_id)
            print(f"  Obtido: {wf['name']} | {len(wf['nodes'])} nos")
            wf_fixed = FIXERS[name](wf)
            result = put_wf(wf_id, wf_fixed)
            print(f"  OK: {result['name']} | activo={result['active']} | {len(result['nodes'])} nos")
            ok += 1
        except Exception as e:
            print(f"  FALHOU: {e}")
    print(f"\n{ok}/{len(WF_IDS)} workflows corrigidos.")


if __name__ == "__main__":
    main()
