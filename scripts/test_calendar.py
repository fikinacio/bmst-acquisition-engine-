import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agents.qualification_bot.tools.calendar import get_available_slots, _format_slot_for_display

print("A buscar slots disponíveis no Google Calendar...")
slots = get_available_slots()

if not slots:
    print("Nenhum slot encontrado (verifica permissões do calendário).")
else:
    print(f"{len(slots)} slot(s) encontrado(s):")
    for s in slots:
        print(f"  {s}  →  {_format_slot_for_display(s)}")
