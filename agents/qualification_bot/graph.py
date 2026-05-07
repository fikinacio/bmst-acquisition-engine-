"""
LangGraph state machine for the qualification bot.

Graph is single-turn: each graph.invoke() handles one incoming WhatsApp message
and produces one reply. Conversation state persists in Airtable between turns.

Node flow:
  router → [greeting | q1_team_size | q2_challenge | q3_process | q4_urgency | book_slot]
         ↘ (unknown stage) → END

  q4_urgency → qualify_pass → book_slot → END   (score >= QUALIFY_THRESHOLD)
             → qualify_fail → END               (score < QUALIFY_THRESHOLD)
             → error_handler → END              (node failure)

  All other Q-nodes → END (next turn starts fresh from the updated current_stage)

Usage:
  from agents.qualification_bot.graph import build_graph
  graph = build_graph()
  result = graph.invoke(initial_state)
"""

from langgraph.graph import StateGraph, END

from agents.qualification_bot.nodes import (
    QUALIFY_THRESHOLD,
    book_slot,
    error_handler,
    greeting,
    nurture_touch_1,
    nurture_touch_2,
    nurture_touch_3,
    q1_team_size,
    q2_challenge,
    q3_process,
    q4_urgency,
    qualify_fail,
    qualify_pass,
    requalify,
    router,
)
from agents.qualification_bot.state import ConversationState

# Stage → node name mapping used by the router conditional edge
_STAGE_TO_NODE: dict[str, str] = {
    "greeting": "greeting",
    "Q1": "q1_team_size",
    "Q2": "q2_challenge",
    "Q3": "q3_process",
    "Q4": "q4_urgency",
    "booking": "book_slot",
    # Nurture outbound stages (WF06) + requalify inbound/outbound
    "nurture_touch_1": "nurture_touch_1",
    "nurture_touch_2": "nurture_touch_2",
    "nurture_touch_3": "nurture_touch_3",
    "requalify": "requalify",
}


def _dispatch_from_router(state: ConversationState) -> str:
    return _STAGE_TO_NODE.get(state.current_stage, END)


def _dispatch_from_q4(state: ConversationState) -> str:
    if state.error:
        return "error_handler"
    if state.qualification_score >= QUALIFY_THRESHOLD:
        return "qualify_pass"
    return "qualify_fail"


def build_graph() -> StateGraph:
    """Compile and return the qualification bot LangGraph."""
    g = StateGraph(ConversationState)

    # Register nodes
    g.add_node("router", router)
    g.add_node("greeting", greeting)
    g.add_node("q1_team_size", q1_team_size)
    g.add_node("q2_challenge", q2_challenge)
    g.add_node("q3_process", q3_process)
    g.add_node("q4_urgency", q4_urgency)
    g.add_node("qualify_pass", qualify_pass)
    g.add_node("qualify_fail", qualify_fail)
    g.add_node("book_slot", book_slot)
    g.add_node("error_handler", error_handler)
    g.add_node("nurture_touch_1", nurture_touch_1)
    g.add_node("nurture_touch_2", nurture_touch_2)
    g.add_node("nurture_touch_3", nurture_touch_3)
    g.add_node("requalify", requalify)

    # Entry point
    g.set_entry_point("router")

    # Router dispatches to the correct Q-node based on current_stage
    g.add_conditional_edges(
        "router",
        _dispatch_from_router,
        {
            "greeting": "greeting",
            "q1_team_size": "q1_team_size",
            "q2_challenge": "q2_challenge",
            "q3_process": "q3_process",
            "q4_urgency": "q4_urgency",
            "book_slot": "book_slot",
            "nurture_touch_1": "nurture_touch_1",
            "nurture_touch_2": "nurture_touch_2",
            "nurture_touch_3": "nurture_touch_3",
            "requalify": "requalify",
            END: END,
        },
    )

    # Single-turn Q nodes — return after producing reply
    g.add_edge("greeting", END)
    g.add_edge("q1_team_size", END)
    g.add_edge("q2_challenge", END)
    g.add_edge("q3_process", END)

    # Q4 branches to pass/fail/error in the same turn
    g.add_conditional_edges(
        "q4_urgency",
        _dispatch_from_q4,
        {
            "qualify_pass": "qualify_pass",
            "qualify_fail": "qualify_fail",
            "error_handler": "error_handler",
        },
    )

    # qualify_pass immediately chains to book_slot (same turn, no extra message needed)
    g.add_edge("qualify_pass", "book_slot")
    g.add_edge("qualify_fail", END)
    g.add_edge("book_slot", END)
    g.add_edge("error_handler", END)
    g.add_edge("nurture_touch_1", END)
    g.add_edge("nurture_touch_2", END)
    g.add_edge("nurture_touch_3", END)
    g.add_edge("requalify", END)

    return g.compile()
