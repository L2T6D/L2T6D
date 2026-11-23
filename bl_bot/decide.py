"""The execute-or-hold decision on a target that already passed the Sharpe gate.

Deciders:
  api     - ask Claude through the Anthropic API (needs ANTHROPIC_API_KEY or `ant auth login`)
  pending - write logs/pending_decision.json and stop; a person or a Claude Code session
            then runs `python -m bl_bot decide --action execute|hold --reason "..."`
  execute - always execute (for testing the plumbing only)
"""
import json

from . import config

SYSTEM = """You are the risk desk for a small paper-traded equity book. A quantitative rule \
(Black-Litterman on analyst price targets, followed by position limits) has proposed new \
target weights, and the proposal already beat the current book on trailing Sharpe. \
Decide whether to EXECUTE the rebalance today or HOLD the current book.

Weigh: how much the book would change (turnover) against how much the rule expects to gain; \
whether the gate's Sharpe edge is large or within noise for a 63-day window; concentration \
and short exposure; whether analyst targets look stale or extreme relative to price; and \
whether trading so soon after the last rebalance is churn. You cannot see news, so do not \
invent any. This is a paper book; be decisive. Give a reason of two to four sentences \
that cites the numbers you relied on."""

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["execute", "hold"]},
        "reason": {"type": "string"},
    },
    "required": ["action", "reason"],
    "additionalProperties": False,
}


def ask_claude(packet):
    import anthropic

    client = anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": config.CLAUDE_EFFORT,
                           "format": {"type": "json_schema", "schema": SCHEMA}},
            system=SYSTEM,
            messages=[{"role": "user", "content":
                       "Today's rebalance proposal:\n\n" + json.dumps(packet, indent=2)}],
        )
    except anthropic.AuthenticationError:
        raise SystemExit("Anthropic API credentials missing or invalid. "
                         "Set ANTHROPIC_API_KEY or run `ant auth login`, or use --decider pending.")
    except anthropic.RateLimitError:
        return {"action": "hold", "reason": "Claude API rate-limited; holding by default.",
                "decided_by": "fallback"}
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        return {"action": "hold", "reason": f"Claude API error ({e.__class__.__name__}); holding by default.",
                "decided_by": "fallback"}

    if resp.stop_reason == "refusal":
        return {"action": "hold", "reason": "Claude declined to answer; holding by default.",
                "decided_by": "fallback"}
    text = "".join(b.text for b in resp.content if b.type == "text")
    out = json.loads(text)
    out["decided_by"] = resp.model
    return out
