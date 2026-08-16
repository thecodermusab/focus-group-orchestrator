"""CLI entry point.

Examples:
  python main.py --brief "Smart coffee machine for busy people" --platform Instagram
  python main.py --mock            # offline demo, no API key needed
"""

import argparse
import pathlib

from focusgroup.llm import make_client
from focusgroup.orchestrator import build_report, run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B-testing focus group of LLM agents")
    parser.add_argument("--brief", default="SmartBrew: an AI-powered coffee machine "
                        "that learns your schedule and brews before you wake up.")
    parser.add_argument("--platform", default="Instagram",
                        choices=["Instagram", "LinkedIn", "X"])
    parser.add_argument("--drafts", type=int, default=3, help="alternative drafts in round 1")
    parser.add_argument("--rounds", type=int, default=4, help="max feedback rounds")
    parser.add_argument("--mock", action="store_true",
                        help="run offline with the deterministic mock LLM")
    parser.add_argument("--out", default="output", help="output directory")
    args = parser.parse_args()

    # optional .env support
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    client = make_client(mock=args.mock)
    state = run_campaign(
        client,
        product_brief=args.brief,
        platform=args.platform,
        n_drafts=args.drafts,
        max_rounds=args.rounds,
    )

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(build_report(state), encoding="utf-8")
    (out / "state.json").write_text(state.to_json(), encoding="utf-8")

    winner = state.drafts[state.approved_draft_id]
    print(f"\n{'='*62}")
    print(f"RESULT: {state.status} — winning draft {winner.draft_id} "
          f"(mean intent {state.mean_intent(winner.draft_id)}/10)")
    print(f"  {winner.headline}")
    print(f"  {winner.body}")
    print(f"\nReport: {out/'report.md'}\nFull state: {out/'state.json'}")


if __name__ == "__main__":
    main()
