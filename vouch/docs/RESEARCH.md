# Why Vouch — the research behind the idea

Short version for the team: we didn't pick this idea by vibes. We studied what actually *wins* AI
hackathons, matched it to what *this* hackathon rewards, and landed on the one shape that is both a
proven winner and feels *natural* to a real user rather than forced for the judges.

## What we looked at

We read the winners (and the broader entry pools) of ~6 recent AI hackathons across two types:

- **Developer / tooling hackathons:** GitLab AI Hackathon, Microsoft AI Dev Days, UiPath AgentHack,
  UC Berkeley Cal Hacks.
- **General / consumer hackathons** (as a control): Agno Global Agent Hackathon, a Google Cloud one.

## What we found

1. **In developer/tooling hackathons, "guardian" projects win** — things that *validate, gate, or
   verify* an AI's output, not things that merely generate. Evidence:
   - GitLab's grand prize: a knowledge system that shipped with 43 tests; a judge said "this feels
     like a product, not a hackathon project."
   - Microsoft's grand prize: a multi-agent **release gate** returning a *confidence score* + a
     plain-English risk brief instead of pass/fail.
   - UiPath's grand prize: **"Gauntlet — go safe or go home"**, and its entire testing track went to
     validation/QA tools (FlakeWarden, a "pre-flight check" agent, "SelfHeal QA").
2. **In consumer hackathons it flips** — polished consumer apps win (a social network, a recipe
   helper). Verification barely places. So *the type of hackathon decides what wins.*
3. **One invariant everywhere: production-readiness.** The winner always *feels finished.* Polish and
   reliability beat a clever half-working demo, every time.

## Why that points at Vouch

This hackathon (Bright Data) is squarely a **developer/tooling** event: it mandates their scraper
tooling, requires a coding-agent workflow, has a *clean-code* track, and scores you explicitly on
**reliability and self-healing**. That's GitLab/UiPath territory, not Agno territory — so the winning
move is the guardian archetype.

Bright Data's headline feature is **self-healing scrapers**. The open problem underneath it: a heal
can be **silently wrong** — it can start extracting the wrong field while looking perfectly fine
(right row count, right format). So the natural guardian to build here is one that **validates a
self-heal before it's committed.** That's the exact "confidence-score-that-gates-an-action" shape that
won Microsoft's and UiPath's grand prizes, aimed at the one thing this hackathon is actually about.

## The one non-obvious design decision

A guardian is only *natural* to an end user if the user is about to **do something costly with the
data.** Looking at a price (a tracker) → the user doesn't act, so reliability feels like forced
plumbing. **Committing a price change against real money** (a repricer) → the user acts, so "is this
number trustworthy?" becomes the feature they actually want.

That's why Vouch is a **repricing copilot**, not a tracker. The self-heal surfaces to the seller only
as *"a price change is held because we couldn't confirm a source"* — a decision that just protected
their margin, not a healing animation performed for the judges.

## In one sentence

> Bright Data's scrapers self-heal; Vouch is the guardian that makes sure a heal didn't quietly start
> lying — and it lives inside a repricer, where "don't act on a number you can't trust" is exactly
> what the user came for.
