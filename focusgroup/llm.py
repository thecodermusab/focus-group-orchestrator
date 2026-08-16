"""LLM client wrapper.

Two backends:
  * DeepSeekClient — real calls to DeepSeek's OpenAI-compatible API.
  * MockClient    — deterministic, offline responses so the orchestration
                    logic can be tested (pytest / demo) without an API key.

Every agent talks to the LLM only through `chat()`, so swapping backends
changes nothing else in the system.
"""

from __future__ import annotations

import json
import os
import re


class LLMError(RuntimeError):
    pass


def extract_json(text: str) -> dict:
    """Parse a JSON object out of an LLM reply (tolerates ```json fences)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"Could not parse JSON from model reply:\n{text}") from e


class DeepSeekClient:
    """Thin wrapper over DeepSeek's OpenAI-compatible chat API."""

    def __init__(self, model: str = "deepseek-chat", temperature: float = 0.8):
        from openai import OpenAI  # imported lazily so mock mode needs no SDK

        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise LLMError(
                "DEEPSEEK_API_KEY is not set. Export it or put it in a .env file."
            )
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = model
        self.temperature = temperature

    def chat(self, system: str, user: str, agent: str = "", json_mode: bool = False) -> str:
        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **kwargs,
        )
        return resp.choices[0].message.content


class MockClient:
    """Deterministic offline backend.

    Scripted so a full campaign exercises every orchestration path:
      round 1 -> personas split, manager orders a revision and dynamically
                 routes only to the dissatisfied personas;
      round 2 -> reconsulted personas are satisfied, manager approves.
    """

    def __init__(self):
        self.persona_calls: dict[str, int] = {}

    def chat(self, system: str, user: str, agent: str = "", json_mode: bool = False) -> str:
        if agent == "copywriter":
            if "REVISION REQUEST" in user:
                return json.dumps({"drafts": [{
                    "headline": "Fresh coffee, zero effort — and zero waste.",
                    "body": "SmartBrew learns your schedule, brews before you wake, "
                            "and its compostable pods cut waste by 80%. "
                            "Free shipping this week.",
                    "angle": "convenience + sustainability (revised per focus group)",
                }]})
            return json.dumps({"drafts": [
                {"headline": "Wake up to genius coffee.",
                 "body": "SmartBrew's AI learns your routine and brews the perfect cup "
                         "before your alarm rings.",
                 "angle": "tech-forward convenience"},
                {"headline": "Your mornings, upgraded.",
                 "body": "Busy schedule? SmartBrew has your coffee ready when you are. "
                         "Sleek, silent, smart.",
                 "angle": "professional lifestyle"},
                {"headline": "Coffee made simple.",
                 "body": "One button. Perfect coffee. Every time. SmartBrew keeps it easy.",
                 "angle": "simplicity"},
            ]})

        if agent in ("genz", "professional", "elderly"):
            n = self.persona_calls.get(agent, 0)
            self.persona_calls[agent] = n + 1
            first_round = n < 3  # 3 drafts evaluated in round 1
            if agent == "genz":
                score = 4 if first_round else 9
                return json.dumps({
                    "emotional_reaction": "kinda mid tbh" if first_round else "ok this slaps",
                    "critique": "Feels like an ad my dad would like. Nothing about values, "
                                "sustainability, or why I should care."
                                if first_round else
                                "Compostable pods + it just works? That's actually cool.",
                    "purchase_intent": score,
                    "would_buy": not first_round,
                })
            if agent == "elderly":
                score = 3 if first_round else 8
                return json.dumps({
                    "emotional_reaction": "confused" if first_round else "reassured",
                    "critique": "What is 'AI learns your routine'? Sounds complicated and "
                                "possibly expensive."
                                if first_round else
                                "'Zero effort' and free shipping — clear and appealing.",
                    "purchase_intent": score,
                    "would_buy": not first_round,
                })
            # professional is happy from the start
            return json.dumps({
                "emotional_reaction": "interested",
                "critique": "Clean value proposition, speaks to my schedule.",
                "purchase_intent": 8,
                "would_buy": True,
            })

        if agent == "manager":
            if "Round 1" in user:
                return json.dumps({
                    "action": "revise",
                    "selected_draft": "A",
                    "dropped_drafts": ["B", "C"],
                    "reconsult": ["genz", "elderly"],
                    "revision_instructions": "Keep the convenience hook but add a "
                        "sustainability angle for Gen-Z and simpler, concrete language "
                        "with a price/offer signal for the elderly customer.",
                    "rationale": "Draft A scored highest overall but Gen-Z (4/10) and the "
                        "elderly persona (3/10) rejected it; the professional persona is "
                        "already convinced, so only the two dissatisfied personas need "
                        "to re-evaluate the revision.",
                })
            return json.dumps({
                "action": "approve",
                "selected_draft": "A2",
                "dropped_drafts": [],
                "reconsult": [],
                "revision_instructions": "",
                "rationale": "All consulted personas now report purchase intent >= 8; "
                             "conversion goal met.",
            })

        raise LLMError(f"MockClient: unknown agent '{agent}'")


def make_client(mock: bool = False):
    return MockClient() if mock else DeepSeekClient()
