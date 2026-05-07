"""
Testa o fluxo de booking em dois modos:

  Unit (default)  — chama os nos directamente em processo, mocka Calendar e LLM.
                    Rapido, sem chamadas externas.

  Integration     — testa via HTTP contra servidor real (Google Calendar real,
                    LLM real). Usa --integration para activar.
                    Cria evento real no calendario — apaga-o no final.

Uso:
    python scripts/test_booking_flow.py            # unit tests
    python scripts/test_booking_flow.py --integration  # HTTP + real Calendar
"""
import sys
import json
import argparse
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

# Fix Windows CP1252 console — força UTF-8 no stdout
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

# ── Constantes de teste ───────────────────────────────────────────────────────

FAKE_SLOT_1 = "2026-05-07T09:00:00+01:00"
FAKE_SLOT_2 = "2026-05-07T10:00:00+01:00"
FAKE_EVENT_ID = "evt_TEST_FAKE_001"

BASE_STATE_FIELDS = {
    "id": "recBOOKTEST01",
    "Name": "Luanda Tech Lda",
    "contact_name": "Carlos Mendes",
    "whatsapp_number": "244912345678",
    "sector": "Tecnologia",
    "state": "lead",
    "conversation_stage": "booking",
    "qualification_score": 82,
    "team_size": "15",
    "main_challenge": "gestao de encomendas manual",
    "priority_process": "facturacao",
    "urgency_level": "high",
    "available_slot_1": None,
    "available_slot_2": None,
}

# ── Helpers ───────────────────────────────────────────────────────────────────

passed = 0
failed = 0


def ok(label: str):
    global passed
    passed += 1
    print(f"  [OK] {label}")


def fail(label: str, reason: str):
    global failed
    failed += 1
    print(f"  [FAIL] {label}: {reason}")


def assert_eq(label, got, expected):
    if got == expected:
        ok(label)
    else:
        fail(label, f"esperado {expected!r}, recebi {got!r}")


def assert_truthy(label, value):
    if value:
        ok(label)
    else:
        fail(label, f"valor vazio/falso: {value!r}")


# ── UNIT TESTS ────────────────────────────────────────────────────────────────

def _fake_llm_response(reply: str, new_stage: str, extracted: dict = None) -> dict:
    return {
        "reply_text": reply,
        "new_stage": new_stage,
        "extracted": extracted or {},
    }


def _make_state(overrides: dict = None):
    from agents.qualification_bot.state import ConversationState
    fields = {**BASE_STATE_FIELDS, **(overrides or {})}
    return ConversationState(
        company_id=fields["id"],
        company_name=fields["Name"],
        contact_name=fields["contact_name"],
        whatsapp_number=fields["whatsapp_number"],
        sector=fields["sector"],
        current_stage=fields["conversation_stage"],
        qualification_score=fields["qualification_score"],
        team_size=fields["team_size"],
        main_challenge=fields["main_challenge"],
        priority_process=fields["priority_process"],
        urgency_level=fields["urgency_level"],
        available_slot_1=fields.get("available_slot_1"),
        available_slot_2=fields.get("available_slot_2"),
        incoming_message=fields.get("incoming_message", ""),
    )


def run_unit_tests():
    print("\n" + "="*60)
    print("UNIT TESTS — nos em processo (Calendar e LLM mockados)")
    print("="*60)

    from agents.qualification_bot import nodes

    # ── U1: _present_slots com disponibilidade ────────────────────────────────
    print("\n[U1] _present_slots — Calendar tem 2 slots")
    with (
        patch("agents.qualification_bot.nodes.cal.get_available_slots",
              return_value=[FAKE_SLOT_1, FAKE_SLOT_2]),
        patch("agents.qualification_bot.nodes._call_llm",
              return_value=_fake_llm_response("Opcao 1: 7/Mai 09h00  |  Opcao 2: 7/Mai 10h00", "booking",
                                              {"slot_1": FAKE_SLOT_1, "slot_2": FAKE_SLOT_2})),
    ):
        state = _make_state()
        result = nodes._present_slots(state)

    assert_eq("new_stage = booking", result.new_stage, "booking")
    assert_truthy("reply_text preenchido", result.reply_text)
    assert_eq("available_slot_1 guardado no state", result.available_slot_1, FAKE_SLOT_1)
    assert_eq("available_slot_2 guardado no state", result.available_slot_2, FAKE_SLOT_2)
    assert_eq("airtable_updates tem available_slot_1",
              result.airtable_updates.get("available_slot_1"), FAKE_SLOT_1)

    # ── U2: _present_slots sem disponibilidade ────────────────────────────────
    print("\n[U2] _present_slots — Calendar sem slots (fallback humano)")
    with patch("agents.qualification_bot.nodes.cal.get_available_slots", return_value=[]):
        state = _make_state()
        result = nodes._present_slots(state)

    assert_eq("new_stage = booking (aguarda humano)", result.new_stage, "booking")
    assert_truthy("fallback reply_text", result.reply_text)

    # ── U3: _confirm_booking — escolha clara opcao 1 ─────────────────────────
    print("\n[U3] _confirm_booking — utilizador diz '1'")
    with (
        patch("agents.qualification_bot.nodes._call_llm", side_effect=[
            _fake_llm_response("", "booking", {"chosen_slot": "1"}),
            _fake_llm_response("Confirmado! Quarta 7 Mai as 09h00.", "audit_scheduled"),
        ]),
        patch("agents.qualification_bot.nodes.cal.book_slot",
              return_value=FAKE_EVENT_ID) as mock_book,
    ):
        state = _make_state({
            "available_slot_1": FAKE_SLOT_1,
            "available_slot_2": FAKE_SLOT_2,
            "incoming_message": "1",
        })
        result = nodes._confirm_booking(state)

    assert_eq("new_stage = audit_scheduled", result.new_stage, "audit_scheduled")
    assert_eq("new_state = audit_scheduled", result.new_state, "audit_scheduled")
    assert_truthy("reply_text preenchido", result.reply_text)
    assert_eq("cal.book_slot chamado com slot_1",
              mock_book.call_args[0][0], FAKE_SLOT_1)
    assert_eq("airtable_updates booked_slot",
              result.airtable_updates.get("booked_slot"), FAKE_SLOT_1)
    assert_eq("airtable_updates calendar_event_id",
              result.airtable_updates.get("calendar_event_id"), FAKE_EVENT_ID)

    # ── U4: _confirm_booking — escolha clara opcao 2 ─────────────────────────
    print("\n[U4] _confirm_booking — utilizador diz 'prefiro o segundo horario'")
    with (
        patch("agents.qualification_bot.nodes._call_llm", side_effect=[
            _fake_llm_response("", "booking", {"chosen_slot": "2"}),
            _fake_llm_response("Confirmado! Quarta 7 Mai as 10h00.", "audit_scheduled"),
        ]),
        patch("agents.qualification_bot.nodes.cal.book_slot",
              return_value=FAKE_EVENT_ID) as mock_book,
    ):
        state = _make_state({
            "available_slot_1": FAKE_SLOT_1,
            "available_slot_2": FAKE_SLOT_2,
            "incoming_message": "prefiro o segundo horario",
        })
        result = nodes._confirm_booking(state)

    assert_eq("new_stage = audit_scheduled", result.new_stage, "audit_scheduled")
    assert_eq("cal.book_slot chamado com slot_2",
              mock_book.call_args[0][0], FAKE_SLOT_2)

    # ── U5: _confirm_booking — resposta ambigua ───────────────────────────────
    print("\n[U5] _confirm_booking — resposta ambigua (re-apresenta opcoes)")
    with patch("agents.qualification_bot.nodes._call_llm", side_effect=[
        _fake_llm_response("", "booking", {"chosen_slot": "unclear"}),
        _fake_llm_response("Qual prefere, opcao 1 ou 2?", "booking"),
    ]):
        state = _make_state({
            "available_slot_1": FAKE_SLOT_1,
            "available_slot_2": FAKE_SLOT_2,
            "incoming_message": "hmm nao sei",
        })
        result = nodes._confirm_booking(state)

    assert_eq("new_stage = booking (re-apresentou)", result.new_stage, "booking")
    assert_truthy("reply_text re-apresentacao", result.reply_text)

    # ── U6: book_slot dispatcher ──────────────────────────────────────────────
    print("\n[U6] book_slot — dispatch: sem slots -> _present_slots")
    with (
        patch("agents.qualification_bot.nodes._present_slots") as mock_present,
        patch("agents.qualification_bot.nodes._confirm_booking") as mock_confirm,
    ):
        mock_present.return_value = MagicMock()
        state = _make_state({"available_slot_1": None, "incoming_message": ""})
        nodes.book_slot(state)

    assert_eq("_present_slots chamado", mock_present.called, True)
    assert_eq("_confirm_booking NAO chamado", mock_confirm.called, False)

    print("\n[U7] book_slot — dispatch: com slots + reply -> _confirm_booking")
    with (
        patch("agents.qualification_bot.nodes._present_slots") as mock_present,
        patch("agents.qualification_bot.nodes._confirm_booking") as mock_confirm,
    ):
        mock_confirm.return_value = MagicMock()
        state = _make_state({
            "available_slot_1": FAKE_SLOT_1,
            "incoming_message": "1",
        })
        nodes.book_slot(state)

    assert_eq("_confirm_booking chamado", mock_confirm.called, True)
    assert_eq("_present_slots NAO chamado", mock_present.called, False)


# ── INTEGRATION TESTS ─────────────────────────────────────────────────────────

def run_integration_tests():
    import requests

    BASE_URL = "http://127.0.0.1:8000"

    print("\n" + "="*60)
    print("INTEGRATION TESTS — HTTP real, Calendar real, LLM real")
    print("="*60)

    try:
        health = requests.get(f"{BASE_URL}/health", timeout=5).json()
        assert health["status"] == "ok"
        print(f"  Servidor OK: {BASE_URL}")
    except Exception as e:
        fail("servidor acessivel", str(e))
        print("  Inicia com: uvicorn api.main:app --host 127.0.0.1 --port 8000")
        return

    def qualify(fields_override, message):
        company = {"id": BASE_STATE_FIELDS["id"], "fields": {
            **{k: v for k, v in BASE_STATE_FIELDS.items() if k != "id"},
            **fields_override,
        }}
        resp = requests.post(
            f"{BASE_URL}/qualify",
            json={"company_record": company, "incoming_message": message},
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    # ── I1: Apresentar slots ──────────────────────────────────────────────────
    print("\n[I1] Apresentar slots (Google Calendar real)")
    try:
        r = qualify({"conversation_stage": "booking", "available_slot_1": None, "available_slot_2": None}, "")
        assert_eq("new_stage = booking", r["new_stage"], "booking")
        assert_truthy("reply_text tem opcoes", r["reply_text"])
        slot_1 = r["updates"].get("available_slot_1")
        slot_2 = r["updates"].get("available_slot_2")
        assert_truthy("available_slot_1 guardado", slot_1)
        assert_truthy("available_slot_2 guardado", slot_2)
        print(f"    Bot: {r['reply_text'][:120]}...")
        print(f"    Slots guardados: {slot_1} / {slot_2}")
    except Exception as e:
        fail("I1 apresentar slots", str(e))
        slot_1, slot_2 = FAKE_SLOT_1, FAKE_SLOT_2

    # ── I2: Confirmar opcao 1 (cria evento real) ──────────────────────────────
    print("\n[I2] Confirmar opcao 1 (cria evento no Google Calendar)")
    booked_event_id = None
    try:
        r = qualify({
            "conversation_stage": "booking",
            "available_slot_1": slot_1,
            "available_slot_2": slot_2,
        }, "1")
        assert_eq("new_stage = audit_scheduled", r["new_stage"], "audit_scheduled")
        assert_truthy("reply_text confirmacao", r["reply_text"])
        booked_event_id = r["updates"].get("calendar_event_id")
        assert_truthy("calendar_event_id presente", booked_event_id)
        print(f"    Bot: {r['reply_text'][:120]}...")
        print(f"    Evento criado: {booked_event_id}")
    except Exception as e:
        fail("I2 confirmar opcao 1", str(e))

    # Limpa evento de teste do Calendar
    if booked_event_id:
        try:
            from agents.qualification_bot.tools.calendar import _get_service
            import os
            svc = _get_service()
            cal_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
            svc.events().delete(calendarId=cal_id, eventId=booked_event_id).execute()
            print(f"    Evento de teste apagado: {booked_event_id}")
        except Exception as e:
            print(f"    Aviso: nao foi possivel apagar o evento de teste: {e}")

    # ── I3: Resposta ambigua ──────────────────────────────────────────────────
    print("\n[I3] Resposta ambigua (bot deve re-apresentar opcoes)")
    try:
        r = qualify({
            "conversation_stage": "booking",
            "available_slot_1": slot_1,
            "available_slot_2": slot_2,
        }, "hmm nao sei bem qual")
        assert_eq("new_stage = booking (re-apresentou)", r["new_stage"], "booking")
        assert_truthy("reply_text re-apresentacao", r["reply_text"])
        print(f"    Bot: {r['reply_text'][:120]}...")
    except Exception as e:
        fail("I3 resposta ambigua", str(e))

    # ── I4: Content Engine ────────────────────────────────────────────────────
    print("\n[I4] Content Engine (/generate-content)")
    try:
        resp = requests.post(f"{BASE_URL}/generate-content", json={
            "company_name": "Empresa Teste",
            "sector": "Logistica",
            "pain_description": "Gestao manual de rotas e stocks",
            "audit_notes": "20 colaboradores. Perdem 2h/dia em reconciliacao de stocks.",
            "market": "Angola",
        }, timeout=90)
        r = resp.json()
        assert_truthy("linkedin_body", r.get("linkedin_body"))
        assert_truthy("instagram_body", r.get("instagram_body"))
        li = r["linkedin_body"]
        ig = r["instagram_body"]
        print(f"    LinkedIn ({len(li)} chars): {li[:100]}...")
        print(f"    Instagram ({len(ig)} chars): {ig[:80]}...")
        assert_truthy("instagram termina com audit.biscaplus.com",
                      "audit.biscaplus.com" in ig)
    except Exception as e:
        fail("I4 content engine", str(e))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--integration", action="store_true",
                        help="Corre integration tests (HTTP + Calendar real)")
    args = parser.parse_args()

    if args.integration:
        run_integration_tests()
    else:
        run_unit_tests()

    print(f"\n{'='*60}")
    print(f"Resultado: {passed} OK  |  {failed} falhados")
    print("="*60)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
