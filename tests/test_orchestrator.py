"""Tests run fully offline against the deterministic MockClient.

They verify the three course requirements:
  1. State management  — all drafts/feedback/decisions accumulate in one state
  2. Feedback loop     — round 1 revise -> round 2 approve
  3. Dynamic routing   — only dissatisfied personas are re-consulted in round 2
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from focusgroup.llm import MockClient, extract_json
from focusgroup.orchestrator import build_report, run_campaign


def run():
    return run_campaign(
        MockClient(),
        product_brief="SmartBrew AI coffee machine",
        platform="Instagram",
        verbose=False,
    )


def test_feedback_loop_terminates_with_approval():
    state = run()
    assert state.status == "approved"
    assert state.round_num == 2  # revise in round 1, approve in round 2
    actions = [d.action for d in state.decisions]
    assert actions == ["revise", "approve"]


def test_dynamic_routing_reconsults_only_dissatisfied_personas():
    state = run()
    round1 = state.decisions[0]
    assert sorted(round1.reconsult) == ["elderly", "genz"]  # professional was satisfied
    round2_personas = {f.persona for f in state.feedback_for_round(2)}
    assert round2_personas == {"genz", "elderly"}
    assert "professional" not in round2_personas


def test_state_management_preserves_full_history():
    state = run()
    assert set(state.drafts) == {"A", "B", "C", "A2"}
    assert state.drafts["A2"].parent_id == "A"
    assert len(state.feedback) == 3 * 3 + 2  # 3 personas x 3 drafts + 2 reconsults
    assert state.approved_draft_id == "A2"
    assert state.mean_intent("A2") > state.mean_intent("A")


def test_report_contains_decision_log_and_winner():
    state = run()
    report = build_report(state)
    assert "Winning ad" in report
    assert "REVISE" in report and "APPROVE" in report
    assert state.drafts["A2"].headline in report


def test_extract_json_handles_code_fences():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('noise {"a": 1} noise') == {"a": 1}


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failures else 0)
