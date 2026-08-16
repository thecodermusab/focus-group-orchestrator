"""Shared campaign state — the single source of truth passed between agents.

This is the project's State Management layer: every agent reads from and
writes into one CampaignState object, and the full history (drafts, feedback,
decisions) is preserved so the orchestrator can reason over past rounds.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json


@dataclass
class Draft:
    draft_id: str            # e.g. "A", "B", "C" (revisions: "A2", "A3", ...)
    parent_id: str | None    # which draft this revises, None for originals
    round_created: int
    headline: str
    body: str
    angle: str               # the creative angle the copywriter used

    def render(self) -> str:
        return f"[{self.draft_id}] {self.headline}\n{self.body}"


@dataclass
class PersonaFeedback:
    persona: str             # "genz" | "professional" | "elderly"
    draft_id: str
    round_num: int
    emotional_reaction: str
    critique: str
    purchase_intent: int     # 1-10
    would_buy: bool


@dataclass
class Decision:
    """One entry in the Campaign Manager's decision log (audit trail)."""
    round_num: int
    action: str              # "revise" | "approve" | "drop"
    selected_draft: str | None
    dropped_drafts: list[str]
    reconsult: list[str]     # personas dynamically routed to in the next round
    revision_instructions: str
    rationale: str


@dataclass
class CampaignState:
    product_brief: str
    platform: str
    round_num: int = 0
    drafts: dict[str, Draft] = field(default_factory=dict)
    active_draft_ids: list[str] = field(default_factory=list)
    feedback: list[PersonaFeedback] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    approved_draft_id: str | None = None
    status: str = "running"  # "running" | "approved" | "max_rounds_reached"

    # ---- convenience accessors used by agents -------------------------

    def active_drafts(self) -> list[Draft]:
        return [self.drafts[d] for d in self.active_draft_ids]

    def feedback_for_round(self, round_num: int) -> list[PersonaFeedback]:
        return [f for f in self.feedback if f.round_num == round_num]

    def feedback_for_draft(self, draft_id: str) -> list[PersonaFeedback]:
        return [f for f in self.feedback if f.draft_id == draft_id]

    def mean_intent(self, draft_id: str) -> float:
        scores = [f.purchase_intent for f in self.feedback_for_draft(draft_id)]
        return round(sum(scores) / len(scores), 2) if scores else 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)
