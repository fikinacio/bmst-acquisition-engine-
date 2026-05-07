"""
Testa o fluxo completo de qualificação localmente.
Simula 5 turnos de conversa: greeting → Q1 → Q2 → Q3 → Q4 → resultado.

Uso:
    python scripts/test_qualify_flow.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import requests

BASE_URL = "http://127.0.0.1:8000"

# Registo inicial da empresa (simula o que vem do Airtable)
company = {
    "id": "recTESTE001",
    "fields": {
        "Name": "Luanda Tech Lda",
        "contact_name": "Carlos Mendes",
        "whatsapp_number": "244912345678",
        "sector": "Tecnologia",
        "state": "prospect",
        "conversation_stage": "greeting",
        "qualification_score": 0,
        "no_response_count": 0,
    }
}

conversation = [
    ("greeting",  "Olá, boa tarde!"),
    ("Q1",        "Somos 15 pessoas na empresa"),
    ("Q2",        "O maior problema é a gestão de encomendas, tudo é manual"),
    ("Q3",        "O processo de facturação demora 3 dias para cada cliente"),
    ("Q4",        "Queremos resolver isso nos próximos 2 meses, temos orçamento"),
]

print(f"{'='*60}")
print(f"TESTE DO FLUXO DE QUALIFICAÇÃO — {company['fields']['Name']}")
print(f"{'='*60}\n")

for expected_stage, user_message in conversation:
    # Garante que o stage no registo está correcto para este turno
    company["fields"]["conversation_stage"] = expected_stage

    payload = {
        "company_record": company,
        "incoming_message": user_message,
    }

    print(f"[STAGE: {expected_stage}] Utilizador: {user_message!r}")

    resp = requests.post(f"{BASE_URL}/qualify", json=payload, timeout=30)

    if resp.status_code != 200:
        print(f"  ERRO {resp.status_code}: {resp.text[:300]}\n")
        break

    data = resp.json()
    reply   = data.get("reply_text", "")
    new_stage = data.get("new_stage", "?")
    new_state = data.get("new_state", "?")
    updates   = data.get("updates", {})

    print(f"  Bot:       {reply}")
    print(f"  new_stage: {new_stage}  |  new_state: {new_state}")
    if updates:
        print(f"  updates:   {json.dumps(updates, ensure_ascii=False)}")
    print()

    # Avança o stage para o próximo turno (simula o que o n8n faria no Airtable)
    company["fields"]["conversation_stage"] = new_stage
    company["fields"].update(updates)

print("="*60)
print("Teste concluído.")
