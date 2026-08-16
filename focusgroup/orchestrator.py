"""The orchestrator: runs the feedback loop and applies dynamic routing.

Flow per campaign:
  1. Copywriter produces N alternative drafts.
  2. Focus group: every persona evaluates every draft (round 1).
  3. Campaign Manager reads ALL feedback from shared state and decides:
       - approve  -> loop ends, report written
       - revise   -> copywriter rewrites the selected draft (reflection),
                     and ONLY the personas the manager lists in `reconsult`
                     re-evaluate it (dynamic routing — the set of agents that
                     runs next is chosen by an LLM decision, not hard-coded).
  4. Repeat until approval or max_rounds.
"""

from __future__ import annotations

from .agents import PERSONAS, copywriter_create, copywriter_revise, manager_decide, persona_evaluate
from .state import CampaignState


def log(msg: str, verbose: bool) -> None:
    if verbose:
        print(msg, flush=True)


def run_campaign(
    client,
    product_brief: str,
    platform: str = "Instagram",
    n_drafts: int = 3,
    max_rounds: int = 4,
    verbose: bool = True,
) -> CampaignState:
    state = CampaignState(product_brief=product_brief, platform=platform)

    while state.round_num < max_rounds:
        state.round_num += 1
        log(f"\n{'='*62}\nROUND {state.round_num}\n{'='*62}", verbose)

        # -- 1. Copywriter -------------------------------------------------
        if state.round_num == 1:
            drafts = copywriter_create(client, state, n_drafts)
            log(f"[copywriter] produced {len(drafts)} alternative drafts", verbose)
        else:
            decision = state.decisions[-1]
            drafts = [copywriter_revise(client, state, decision)]
            log(f"[copywriter] revised {decision.selected_draft} -> {drafts[0].draft_id}", verbose)

        for d in drafts:
            state.drafts[d.draft_id] = d
        state.active_draft_ids = [d.draft_id for d in drafts]

        # -- 2. Focus group (dynamically routed after round 1) -------------
        if state.round_num == 1:
            personas_to_run = list(PERSONAS)
        else:
            personas_to_run = state.decisions[-1].reconsult or list(PERSONAS)
        log(f"[router] consulting personas: {', '.join(personas_to_run)}", verbose)

        for draft in state.active_drafts():
            for persona in personas_to_run:
                fb = persona_evaluate(client, state, persona, draft)
                state.feedback.append(fb)
                log(
                    f"  [{persona}] {draft.draft_id}: intent {fb.purchase_intent}/10 "
                    f"— {fb.emotional_reaction}",
                    verbose,
                )

        # -- 3. Campaign manager decides ----------------------------------
        decision = manager_decide(client, state)
        state.decisions.append(decision)
        log(f"[manager] action={decision.action} — {decision.rationale}", verbose)

        if decision.action == "approve" and decision.selected_draft in state.drafts:
            state.approved_draft_id = decision.selected_draft
            state.status = "approved"
            break

    if state.status != "approved":
        state.status = "max_rounds_reached"
        # fall back to the best-scoring draft so the run still produces output
        best = max(state.drafts, key=state.mean_intent)
        state.approved_draft_id = best
    return state


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_report(state: CampaignState) -> str:
    winner = state.drafts[state.approved_draft_id]
    lines = [
        "# Campaign Focus-Group Report",
        "",
        f"**Product brief:** {state.product_brief}",
        f"**Platform:** {state.platform}",
        f"**Status:** {state.status} after {state.round_num} round(s)",
        "",
        "## Winning ad",
        "",
        f"> **{winner.headline}**",
        f"> {winner.body}",
        "",
        f"*Angle:* {winner.angle} — *mean purchase intent:* "
        f"{state.mean_intent(winner.draft_id)}/10",
        "",
        "## Decision log",
        "",
    ]
    for d in state.decisions:
        lines += [
            f"### Round {d.round_num}: {d.action.upper()}",
            f"- Selected: {d.selected_draft} | Dropped: {', '.join(d.dropped_drafts) or '—'}",
            f"- Personas routed to next: {', '.join(d.reconsult) or '— (none / all satisfied)'}",
            f"- Rationale: {d.rationale}",
        ]
        if d.revision_instructions:
            lines.append(f"- Revision instructions: {d.revision_instructions}")
        lines.append("")
    lines += ["## Full focus-group feedback", ""]
    for f in state.feedback:
        lines.append(
            f"- R{f.round_num} · draft {f.draft_id} · **{f.persona}** "
            f"(intent {f.purchase_intent}/10, buy={f.would_buy}): "
            f"*{f.emotional_reaction}* — {f.critique}"
        )
    lines += ["", "## All drafts", ""]
    for d in state.drafts.values():
        rev = f" (revision of {d.parent_id})" if d.parent_id else ""
        lines.append(f"- **{d.draft_id}**{rev}: {d.headline} — {d.body}")
    return "\n".join(lines)
