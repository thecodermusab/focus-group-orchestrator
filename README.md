# Campaign Generator and Focus Group for A/B Testing

**SENG 456 — Agent Orchestration and Multimodal Systems, Term Project (Project #9)**

A dynamic multi-agent orchestration system in which LLM agents critique, audit,
and make decisions with one another. A copywriter agent produces alternative ad
drafts; three customer-persona agents (a Gen-Z student, a busy professional, and
an elderly customer) react as a focus group; a campaign-manager agent reads all
feedback and *decides* what happens next — approve the winner, or send it back
for revision and dynamically choose which personas need to re-evaluate it.
Nothing in the control flow is a hard-coded if/else pipeline: routing and
termination are LLM decisions.

## Architecture

```
                 ┌─────────────────────────────────────────┐
                 │        CampaignState (shared state)      │
                 │ drafts · feedback · decision log · round │
                 └─────────────────────────────────────────┘
                        ▲            ▲             ▲
   product brief        │            │             │
        │          ┌────────┐   ┌─────────┐   ┌─────────┐
        └────────▶ │Copywriter│─▶│ Personas │─▶│ Campaign │
                   │ (create/ │  │ Gen-Z    │  │ Manager  │
                   │  revise) │  │ Profess. │  │ (decide) │
                   └────▲─────┘  │ Elderly  │  └────┬─────┘
                        │        └────▲─────┘       │
                        │             │        approve? ──▶ report.md
                        │   dynamic routing:        │
                        └── revise + "reconsult     │
                            only these personas" ◀──┘
```

## Course requirements → where they live in the code

| Requirement | Implementation |
|---|---|
| **State management** | `focusgroup/state.py` — one `CampaignState` object holds every draft (with version lineage A → A2), all persona feedback, and the manager's decision log; every agent reads/writes only through it. Dumped to `output/state.json` after each run. |
| **Reflection & feedback loops** | `focusgroup/orchestrator.py` — personas critique → manager orders a revision → copywriter rewrites using the critiques (`copywriter_revise`) → re-evaluation. Loops until approval or `--rounds`. |
| **Dynamic routing** | The manager's JSON decision includes `reconsult`: the list of persona agents that run in the next round. Satisfied personas are skipped. The set of agents executed is chosen by an LLM at runtime, not by code. |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then put your DeepSeek key in .env
```

## Run

```bash
# real run (needs DEEPSEEK_API_KEY)
python main.py --brief "SmartBrew: an AI coffee machine that learns your schedule" --platform Instagram

# offline demo — no API key, deterministic mock LLM
python main.py --mock

# options
python main.py --brief "..." --platform LinkedIn --drafts 3 --rounds 4
```

Outputs: `output/report.md` (winning ad + decision log + all feedback) and
`output/state.json` (full machine-readable state).

## Tests

```bash
python tests/test_orchestrator.py      # or: pytest tests/ -v
```

Tests run offline against a deterministic mock LLM and verify: the feedback
loop terminates with an approval, only dissatisfied personas are re-consulted
(dynamic routing), full history is preserved in state, and the report contains
the decision log.

## Project layout

```
main.py                     CLI entry point
focusgroup/state.py         shared state (drafts, feedback, decisions)
focusgroup/agents.py        agent prompts + call functions
focusgroup/orchestrator.py  feedback loop, dynamic routing, report builder
focusgroup/llm.py           DeepSeek client + offline mock client
tests/test_orchestrator.py  offline tests of the orchestration logic
```

## Notes

* Model: `deepseek-chat` via DeepSeek's OpenAI-compatible API.
* No secrets in the repo — the key comes from the `DEEPSEEK_API_KEY`
  environment variable (see `.env.example`).
