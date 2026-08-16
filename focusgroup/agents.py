"""Agent definitions: one system prompt + one call function per agent.

Agents never talk to each other directly — they communicate only through the
shared CampaignState, and the orchestrator decides who runs next (dynamic
routing based on the Campaign Manager's decisions).
"""

from __future__ import annotations

from .llm import extract_json
from .state import CampaignState, Draft, PersonaFeedback, Decision

# ---------------------------------------------------------------------------
# Copywriter
# ---------------------------------------------------------------------------

COPYWRITER_SYSTEM = """You are a senior advertising copywriter.
You write short, punchy ad copy (headline + 2-3 sentence body) for social media.
You take focus-group criticism seriously and revise without ego.
Always answer with ONLY a JSON object, no extra text:
{"drafts": [{"headline": "...", "body": "...", "angle": "..."}]}"""


def copywriter_create(client, state: CampaignState, n_drafts: int = 3) -> list[Draft]:
    """Round 1: produce alternative drafts (the A/B/C test candidates)."""
    user = (
        f"Product brief: {state.product_brief}\n"
        f"Platform: {state.platform}\n\n"
        f"Write {n_drafts} alternative ad drafts, each with a clearly different "
        f"creative angle. Return the JSON schema you were given."
    )
    data = extract_json(client.chat(COPYWRITER_SYSTEM, user, agent="copywriter", json_mode=True))
    drafts = []
    for i, d in enumerate(data["drafts"][:n_drafts]):
        draft = Draft(
            draft_id=chr(ord("A") + i),
            parent_id=None,
            round_created=state.round_num,
            headline=d["headline"],
            body=d["body"],
            angle=d.get("angle", ""),
        )
        drafts.append(draft)
    return drafts


def copywriter_revise(client, state: CampaignState, decision: Decision) -> Draft:
    """Reflection step: rewrite the selected draft using manager + persona feedback."""
    parent = state.drafts[decision.selected_draft]
    persona_notes = "\n".join(
        f"- {f.persona} (intent {f.purchase_intent}/10): {f.critique}"
        for f in state.feedback_for_draft(parent.draft_id)
    )
    user = (
        "REVISION REQUEST\n"
        f"Product brief: {state.product_brief}\n"
        f"Platform: {state.platform}\n\n"
        f"Current draft:\n{parent.render()}\n\n"
        f"Focus-group criticism:\n{persona_notes}\n\n"
        f"Campaign manager's instructions: {decision.revision_instructions}\n\n"
        "Rewrite this ONE draft addressing the criticism while keeping what already "
        "works. Return JSON with exactly one draft."
    )
    data = extract_json(client.chat(COPYWRITER_SYSTEM, user, agent="copywriter", json_mode=True))
    d = data["drafts"][0]
    # A -> A2 -> A3 ... version naming
    base = parent.draft_id.rstrip("0123456789") or parent.draft_id
    version = sum(1 for k in state.drafts if k.rstrip("0123456789") == base) + 1
    return Draft(
        draft_id=f"{base}{version}",
        parent_id=parent.draft_id,
        round_created=state.round_num,
        headline=d["headline"],
        body=d["body"],
        angle=d.get("angle", ""),
    )


# ---------------------------------------------------------------------------
# Customer personas (the focus group)
# ---------------------------------------------------------------------------

PERSONAS: dict[str, str] = {
    "genz": """You are Deniz, 21, a Gen-Z university student. You are chronically online,
value authenticity and sustainability, hate anything that smells like corporate
marketing, and decide in about 3 seconds whether an ad is cringe.""",
    "professional": """You are Selin, 38, a busy mid-career finance professional. You value
your time, respond to clear value propositions and quality signals, and are
skeptical of hype without substance.""",
    "elderly": """You are Ahmet, 68, a retired teacher. You distrust complicated technology
and vague claims, care about price, simplicity and reliability, and respond to
respectful, concrete, plain language.""",
}

PERSONA_TASK = """You just saw this ad. React fully in character.
Always answer with ONLY a JSON object:
{"emotional_reaction": "...", "critique": "...", "purchase_intent": <1-10>, "would_buy": true/false}
purchase_intent: 1 = would never buy, 10 = buying right now.
Be honest and specific about WHY — your critique will be used to improve the ad."""


def persona_evaluate(client, state: CampaignState, persona: str, draft: Draft) -> PersonaFeedback:
    system = PERSONAS[persona] + "\n\n" + PERSONA_TASK
    user = f"Ad shown on {state.platform}:\n\n{draft.render()}"
    data = extract_json(client.chat(system, user, agent=persona, json_mode=True))
    return PersonaFeedback(
        persona=persona,
        draft_id=draft.draft_id,
        round_num=state.round_num,
        emotional_reaction=str(data.get("emotional_reaction", "")),
        critique=str(data.get("critique", "")),
        purchase_intent=max(1, min(10, int(data.get("purchase_intent", 5)))),
        would_buy=bool(data.get("would_buy", False)),
    )


# ---------------------------------------------------------------------------
# Campaign Manager (decision maker + dynamic router)
# ---------------------------------------------------------------------------

MANAGER_SYSTEM = """You are a data-driven campaign manager running an ad focus group.
You decide what happens next; you do NOT write copy yourself.

Rules:
- "approve" a draft only if every persona consulted this round gives it
  purchase_intent >= 7. Otherwise "revise".
- When revising: pick the single most promising draft, drop the weak ones, give
  the copywriter concrete instructions, and list in "reconsult" ONLY the
  personas whose concerns were not yet satisfied (purchase_intent < 7).
  Satisfied personas must not be re-consulted — their time is expensive.
- Always explain your rationale.

Always answer with ONLY a JSON object:
{"action": "revise"|"approve", "selected_draft": "...", "dropped_drafts": [...],
 "reconsult": [...], "revision_instructions": "...", "rationale": "..."}"""


def manager_decide(client, state: CampaignState) -> Decision:
    lines = [f"Round {state.round_num} focus-group results:"]
    for draft in state.active_drafts():
        lines.append(f"\nDraft {draft.draft_id} (mean intent {state.mean_intent(draft.draft_id)}):")
        lines.append(draft.render())
        for f in state.feedback_for_draft(draft.draft_id):
            lines.append(
                f"  - {f.persona}: intent {f.purchase_intent}/10, "
                f"would_buy={f.would_buy} — {f.critique}"
            )
    lines.append(
        "\nPersonas available for reconsultation: genz, professional, elderly.\n"
        "Decide now. Return the JSON schema you were given."
    )
    data = extract_json(client.chat(MANAGER_SYSTEM, "\n".join(lines), agent="manager", json_mode=True))
    reconsult = [p for p in data.get("reconsult", []) if p in PERSONAS]
    return Decision(
        round_num=state.round_num,
        action=data.get("action", "revise"),
        selected_draft=data.get("selected_draft"),
        dropped_drafts=list(data.get("dropped_drafts", [])),
        reconsult=reconsult,
        revision_instructions=str(data.get("revision_instructions", "")),
        rationale=str(data.get("rationale", "")),
    )
