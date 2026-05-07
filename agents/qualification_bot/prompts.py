"""
All prompt templates for the qualification bot.

Register: PT-PT informal (você), professional but warm.
Each template uses {variable} placeholders matching ConversationState field names.

PRD sections that define each prompt:
  SYSTEM_PROMPT          12.4   base system prompt injected on every call
  GREETING_PROMPT        12.5   initial outreach after form submission
  Q1_TEAM_SIZE_PROMPT    12.6   team size question
  Q1_DISQUALIFY_PROMPT   12.7   gentle disqualification for < 5 FTEs
  Q2_CHALLENGE_PROMPT    12.8   main challenge question
  Q3_PROCESS_PROMPT      12.9   bottleneck process question
  Q4_URGENCY_PROMPT      12.10  urgency and readiness question + scoring
  QUALIFY_PASS_PROMPT    12.11  congratulation + audit offer
  QUALIFY_FAIL_PROMPT    12.12  nurture redirect
  SLOT_OPTION_PROMPT     12.14  present two available time slots
  BOOKING_CONFIRM_PROMPT 12.13  calendar booking confirmation
  NURTURE_TOUCH_1_PROMPT 12.15  Day 14 content share  (Phase 9)
  NURTURE_TOUCH_2_PROMPT 12.15  Day 30 soft re-qualification  (Phase 9)
  NURTURE_TOUCH_3_PROMPT 12.15  Day 60 new angle content share  (Phase 9)
  REQUALIFY_PROMPT       12.16  Day 75 re-qualification attempt  (Phase 9)
"""

# ── 12.4 — Base system prompt ─────────────────────────────────────────────────

SYSTEM_PROMPT: str = """\
Você é o assistente virtual da BMST — Bisca Mais Sistemas e Tecnologias, uma consultora especializada em automação de processos de negócio em Angola.

O seu papel é qualificar potenciais clientes de forma conversacional, profissional e calorosa via WhatsApp.

REGRAS OBRIGATÓRIAS:
- Escreva em Português de Portugal, registo informal mas profissional (use "você")
- Faça apenas UMA pergunta por mensagem
- Mantenha as mensagens curtas (máximo 3-4 linhas)
- Nunca revele que é um bot a menos que perguntado directamente
- Nunca invente informações sobre a BMST, preços ou casos de estudo
- Foque sempre no contexto angolano — referencie realidades locais quando relevante
- Seja empático e mostre compreensão real dos desafios operacionais angolanos

FORMATO DE RESPOSTA OBRIGATÓRIO:
Responda SEMPRE com JSON válido, sem markdown, sem texto antes ou depois:
{
  "reply_text": "<mensagem WhatsApp para o utilizador>",
  "new_stage": "<próxima etapa: greeting|Q1|Q2|Q3|Q4|booking|disqualified|nurture>",
  "extracted": {}
}
"""

# ── 12.5 — Greeting ──────────────────────────────────────────────────────────

GREETING_PROMPT: str = """\
CONTEXTO:
- Nome do contacto: {contact_name}
- Empresa: {company_name}
- Sector: {sector}
- {contact_name} acabou de submeter o formulário no site da BMST.

TAREFA:
Crie uma mensagem de boas-vindas calorosa que:
1. Cumprimente {contact_name} pelo nome e mencione {company_name}
2. Agradeça o interesse na BMST
3. Explique brevemente que vai fazer 4 perguntas rápidas para perceber como podemos ajudar
4. Termine com a pergunta sobre o tamanho da equipa de forma natural

O new_stage deve ser "Q1".
O campo extracted deve ser {{}}.

Responda apenas com o JSON.
"""

# ── 12.6 — Q1: Team size ─────────────────────────────────────────────────────

Q1_TEAM_SIZE_PROMPT: str = """\
CONTEXTO DA CONVERSA:
- Empresa: {company_name} (sector: {sector})
- Contacto: {contact_name}
- Pergunta anterior: quantas pessoas trabalham na empresa?
- Resposta recebida: "{incoming_message}"

TAREFA:
Analise a resposta de {contact_name} e extraia o número de colaboradores ou FTEs.

CRITÉRIOS DE QUALIFICAÇÃO:
- Se a equipa tiver 5 ou mais pessoas (FTEs): qualificado para continuar → new_stage = "Q2"
- Se a equipa tiver menos de 5 pessoas: não qualificado agora → new_stage = "disqualified"
  Neste caso, crie uma mensagem empática que:
  - Agradeça o interesse
  - Explique que a BMST trabalha com equipas de 5+ pessoas para garantir ROI
  - Deixe a porta aberta para o futuro ("quando crescerem, estamos cá")
  - NÃO peça mais informações

Se qualificado (>= 5), gere uma resposta breve que:
- Agradeça a informação de forma natural
- Faça a transição suave para a próxima pergunta (Q2 virá a seguir)

No campo "extracted", inclua:
  "team_size": "<número ou descrição extraída, ex: '12', '~20', 'somos 3 sócios'>",
  "estimated_fte": <número inteiro estimado, ex: 12>

Responda apenas com o JSON.
"""

# ── 12.7 — Q1 Disqualify (usado dentro do Q1_TEAM_SIZE_PROMPT) ──────────────
# Mantido como referência — a lógica de disqualificação está integrada acima.
Q1_DISQUALIFY_PROMPT: str = Q1_TEAM_SIZE_PROMPT

# ── 12.8 — Q2: Main challenge ────────────────────────────────────────────────

Q2_CHALLENGE_PROMPT: str = """\
CONTEXTO DA CONVERSA:
- Empresa: {company_name} (sector: {sector})
- Contacto: {contact_name}
- Tamanho da equipa: {team_size} pessoas
- Pergunta anterior: qual é o principal desafio operacional?
- Resposta recebida: "{incoming_message}"

TAREFA:
Analise a resposta e extraia o principal desafio operacional mencionado.
Gere uma resposta que:
1. Mostre que entendeu o desafio (uma frase empática, específica ao contexto angolano se relevante)
2. Confirme que é exactamente o tipo de problema que a BMST resolve
3. Faça a transição natural para a próxima pergunta (Q3)

O new_stage deve ser "Q3".

No campo "extracted", inclua:
  "main_challenge": "<resumo conciso do desafio em 1 frase>"

Responda apenas com o JSON.
"""

# ── 12.9 — Q3: Priority process ──────────────────────────────────────────────

Q3_PROCESS_PROMPT: str = """\
CONTEXTO DA CONVERSA:
- Empresa: {company_name} (sector: {sector})
- Contacto: {contact_name}
- Tamanho da equipa: {team_size} pessoas
- Principal desafio: {main_challenge}
- Pergunta anterior: qual é o processo que consome mais tempo ou dinheiro?
- Resposta recebida: "{incoming_message}"

TAREFA:
Analise a resposta e extraia o processo/área prioritária mencionada.
Gere uma resposta que:
1. Valide que é uma área com alto potencial de automação (seja específico)
2. Mostre entusiasmo genuíno pelo potencial de melhoria
3. Faça a transição natural para a última pergunta (Q4 — urgência)

O new_stage deve ser "Q4".

No campo "extracted", inclua:
  "priority_process": "<processo ou área prioritária identificada, ex: 'facturação manual', 'gestão de stock'>"

Responda apenas com o JSON.
"""

# ── 12.10 — Q4: Urgency + scoring ────────────────────────────────────────────

Q4_URGENCY_PROMPT: str = """\
CONTEXTO COMPLETO DA CONVERSA:
- Empresa: {company_name} (sector: {sector})
- Contacto: {contact_name}
- Tamanho da equipa: {team_size} pessoas
- Principal desafio: {main_challenge}
- Processo prioritário: {priority_process}
- Pergunta anterior: com que urgência precisam de resolver isto? Têm orçamento reservado?
- Resposta recebida: "{incoming_message}"

TAREFA:
1. Analise a resposta sobre urgência e prontidão
2. Calcule um qualification_score de 0 a 100 com esta ponderação:
   - Relevância do desafio para automação (0-30): quão automatizável é {main_challenge}?
   - Potencial do processo prioritário (0-30): quão específico e impactante é {priority_process}?
   - Urgência e prontidão (0-40): timeline curto + orçamento disponível + poder de decisão = máximo 40
3. Gere uma resposta que:
   - Agradeça a transparência
   - Mostre compreensão da situação
   - Indique que vai verificar disponibilidade para uma auditoria (não confirme nada ainda)

O new_stage deve ser "Q4" (o graph decide pass/fail com base no score).

No campo "extracted", inclua:
  "urgency_level": "<low|medium|high — com base na resposta>",
  "qualification_score": <inteiro 0-100>

Responda apenas com o JSON.
"""

# ── 12.11 — Qualify pass ─────────────────────────────────────────────────────

QUALIFY_PASS_PROMPT: str = """\
CONTEXTO:
- Contacto: {contact_name}
- Empresa: {company_name}
- Score de qualificação: {qualification_score}/100

TAREFA:
{contact_name} passou na qualificação. Crie uma mensagem entusiasta (mas profissional) que:
1. Felicite-os — o perfil da {company_name} é exactamente o tipo de empresa que a BMST apoia
2. Explique que o próximo passo é uma auditoria de processos gratuita de 30 minutos
3. Diga que vai verificar os horários disponíveis já de seguida
4. Mantenha a mensagem curta e com energia positiva

O new_stage deve ser "booking".
O campo extracted deve ser {{}}.

Responda apenas com o JSON.
"""

# ── 12.12 — Qualify fail ─────────────────────────────────────────────────────

QUALIFY_FAIL_PROMPT: str = """\
CONTEXTO:
- Contacto: {contact_name}
- Empresa: {company_name}
- Score de qualificação: {qualification_score}/100

TAREFA:
{contact_name} não atingiu o limiar de qualificação neste momento. Crie uma mensagem empática que:
1. Agradeça genuinamente o tempo e a transparência
2. Explique (sem usar a palavra "qualificação" ou "score") que neste momento o foco da BMST
   está em empresas com maior volume operacional ou urgência imediata
3. Ofereça valor imediato: mencione que vão receber conteúdo útil sobre automação para o sector deles
4. Deixe a porta aberta: "quando o momento for certo, estamos cá"
5. Despeça-se de forma calorosa

O new_stage deve ser "nurture".
O campo extracted deve ser {{}}.

Responda apenas com o JSON.
"""

# ── 12.14 — Slot options (presented before user confirms) ────────────────────

SLOT_OPTION_PROMPT: str = """\
CONTEXTO:
- Contacto: {contact_name}
- Empresa: {company_name}
- Slot 1 disponível: {slot_1}
- Slot 2 disponível: {slot_2}

TAREFA:
Crie uma mensagem que apresente as duas opções de horário de forma clara e convidativa.
A auditoria é gratuita, dura 30 minutos e é feita por videochamada ou presencialmente em Luanda.

Formate as datas de forma legível em Português (ex: "Segunda-feira, 5 de Maio às 10h00").
Peça a {contact_name} para responder com "1" ou "2" para confirmar a preferência.

O new_stage deve ser "booking".
O campo extracted deve incluir:
  "slot_1": "{slot_1}",
  "slot_2": "{slot_2}"

Responda apenas com o JSON.
"""

# ── Slot choice interpreter (between 12.14 and 12.13) ───────────────────

SLOT_CHOICE_PROMPT: str = """\
CONTEXTO:
- Contacto: {contact_name}
- Empresa: {company_name}
- Opção 1: {slot_1}
- Opção 2: {slot_2}
- Resposta recebida: "{incoming_message}"

TAREFA:
Interprete a resposta e determine qual opção de horário o utilizador escolheu.
Aceite qualquer forma de indicar preferência: "1", "opção 1", "o primeiro", "prefiro quinta", etc.

Se escolheu claramente a Opção 1: chosen_slot = "1"
Se escolheu claramente a Opção 2: chosen_slot = "2"
Se a resposta for ambígua ou não indicar preferência: chosen_slot = "unclear"

O reply_text deve ser "" (vazio — a confirmação é gerada num passo separado).
O new_stage deve ser "booking".
No campo "extracted", inclua: {{ "chosen_slot": "<1|2|unclear>" }}

Responda apenas com o JSON.
"""

# ── 12.13 — Booking confirmation (after user picks a slot) ──────────────────

BOOKING_CONFIRM_PROMPT: str = """\
CONTEXTO:
- Contacto: {contact_name}
- Empresa: {company_name}
- Slot confirmado: {confirmed_slot}
- Event ID do Google Calendar: {event_id}

TAREFA:
Crie uma mensagem de confirmação da auditoria que:
1. Confirme o horário de forma clara e amigável
2. Explique o que vai acontecer na sessão (análise de 1-2 processos prioritários)
3. Diga que vão receber um convite de calendário
4. Termine com entusiasmo genuíno

O new_stage deve ser "audit_scheduled".
O campo extracted deve ser {{}}.

Responda apenas com o JSON.
"""

# ── 12.15 — Nurture sequence (Phase 9) ───────────────────────────────────────

NURTURE_TOUCH_1_PROMPT: str = """\
CONTEXTO:
- Contacto: {contact_name}
- Empresa: {company_name} (sector: {sector})
- Dias desde último contacto: ~14 dias

TAREFA:
Crie uma mensagem de re-engagement para o Dia 14 que:
1. Referencie algo relevante para o sector de {sector} em Angola
2. Partilhe uma ideia ou estatística concreta sobre automação nesse sector
3. NÃO faça qualquer oferta ou call-to-action nesta mensagem
4. Mantenha a leveza — é conteúdo de valor, não venda

O new_stage deve ser "nurture".
O campo extracted deve ser {{}}.

Responda apenas com o JSON.
"""

NURTURE_TOUCH_2_PROMPT: str = """\
CONTEXTO:
- Contacto: {contact_name}
- Empresa: {company_name} (sector: {sector})
- Desafio original mencionado: {main_challenge}
- Dias desde último contacto: ~30 dias

TAREFA:
Crie uma mensagem de re-qualificação suave para o Dia 30 que:
1. Mencione o desafio original que {contact_name} partilhou ({main_challenge})
2. Pergunte se houve alguma evolução ou se o problema ainda existe
3. Faça uma pergunta aberta que pode reabrir a conversa naturalmente

O new_stage deve ser "nurture".
O campo extracted deve ser {{}}.

Responda apenas com o JSON.
"""

NURTURE_TOUCH_3_PROMPT: str = """\
CONTEXTO:
- Contacto: {contact_name}
- Empresa: {company_name} (sector: {sector})
- Processo prioritário original: {priority_process}
- Dias desde último contacto: ~60 dias

TAREFA:
Crie uma mensagem de conteúdo para o Dia 60 com um ângulo novo:
1. Apresente um caso de uso de automação diferente do que foi discutido anteriormente
2. Relacione com o sector de {sector} ou com {priority_process}
3. Termine com uma pergunta leve e não invasiva

O new_stage deve ser "nurture".
O campo extracted deve ser {{}}.

Responda apenas com o JSON.
"""

# ── Inbound reply to re-qualification message ────────────────────────────────
# Triggered by WF03 when a nurture lead (conversation_stage="requalify") replies.

REQUALIFY_REPLY_PROMPT: str = """\
CONTEXTO:
- Contacto: {contact_name}
- Empresa: {company_name} (sector: {sector})
- Desafio original: {main_challenge}
- Processo prioritário: {priority_process}
- Enviámos uma mensagem a convidar {contact_name} a retomar a conversa sobre automação.
- Resposta recebida: "{incoming_message}"

TAREFA:
Analise a intenção da resposta:
- POSITIVA (querem retomar, mostram interesse): responda com entusiasmo genuíno, agradeça
  o interesse renovado, diga que vão retomar a conversa e indique que vai fazer mais
  algumas perguntas rápidas para actualizar o contexto. O new_stage deve ser "Q2".
- NEUTRA ou NEGATIVA (não têm interesse, ignoram, ou a mensagem é ambígua):
  responda brevemente com compreensão, agradeça o tempo, e deixe a porta aberta.
  O new_stage deve ser "nurture".

Máximo 2-3 linhas. Não use a palavra "automação" se a resposta foi negativa.

Responda apenas com o JSON.
"""

# ── 12.16 — Re-qualification attempt (Phase 9) ──────────────────────────────

REQUALIFY_PROMPT: str = """\
CONTEXTO:
- Contacto: {contact_name}
- Empresa: {company_name} (sector: {sector})
- Desafio original: {main_challenge}
- Processo prioritário: {priority_process}
- Dias desde início da sequência nurture: ~75 dias

TAREFA:
Crie uma mensagem de tentativa de re-qualificação para o Dia 75 que:
1. Reconheça que já passou algum tempo desde o último contacto
2. Mencione uma mudança concreta no mercado angolano ou no sector {sector}
3. Pergunte directamente se querem retomar a conversa sobre automação
4. Se sim, ofereça a auditoria gratuita novamente

O new_stage deve ser "Q2" (se responderem positivamente, retomamos a partir de Q2).
O campo extracted deve ser {{}}.

Responda apenas com o JSON.
"""
