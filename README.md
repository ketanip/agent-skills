# agent-skills

> Production playbooks for AI coding agents. Not prompts — reference material your agent reads *before* it writes code, so it stops guessing at your conventions and starts following them.

```bash
npx skills add ketanip/agent-skills                        # the whole collection
npx skills add ketanip/agent-skills --skill meta-pixel     # or just one
```

[![skills.sh](https://skills.sh/b/ketanip/agent-skills)](https://skills.sh/ketanip/agent-skills)

> Works with Claude Code, Cursor, Copilot, Windsurf, Cline — any agent that supports [skills.sh](https://skills.sh).

---

## The problem these solve

Your agent is a very fast engineer with no memory and no access to the decisions your team made last quarter.

So every new chat, it guesses. Different folder structure than last time. A response envelope it invented on the spot. A Meta Pixel event with the currency as `'$'` — which, by the way, does not throw, does not warn, and does not work.

The failure isn't that the agent is bad at code. It's that **the knowledge lives in your head and never makes it into the context window.**

A skill is that knowledge, written down once, in a form the agent loads automatically when the work calls for it. Same conventions, every session, every teammate, every agent.

---

## The skills

### [`nestjs-prisma-rest-superpowers`](skills/nestjs-prisma-rest-superpowers) — production NestJS + Prisma REST APIs

Consistent folder structure, DTOs with Swagger decorators on every field, a uniform response envelope, Prisma patterns that don't leak, and a complete **dynamic query engine** — `?filter={"AND":[...]}` with 12 operators, relation filtering, complexity guards, and unit tests. The kind of filtering system that takes a senior engineer two days; your agent generates it in one pass.

Six reference files, loaded on demand. → [Full details](skills/nestjs-prisma-rest-superpowers)

### [`meta-pixel`](skills/meta-pixel) — Meta Pixel tracking that actually works

`fbq()` never throws. `value: '5000,00'`, `currency: '$'`, a `contents` entry missing its `quantity` — all accepted silently, while your ad optimization quietly starves and catalog ads fail to match a single product. You find out six weeks later.

This skill treats parameter shape as the load-bearing part of the job and ships a **linter** that catches every malformed pattern Meta's docs call out, plus the multi-pixel over-firing trap. Zero dependencies, CI-ready.

Five reference files + bundled tooling. → [Full details](skills/meta-pixel)

### [`meta-conversions-api`](skills/meta-conversions-api) — server-side CAPI events that actually match

`200 OK` with `events_received: 1` is not proof of anything. The event can land, count, and still be unattributed and unoptimizable. The trap is that the browser Pixel hashes your PII for you and the server does not — so `user_data` must be normalized and SHA-256'd yourself, while `fbp`/`fbc`/IP/user-agent must be sent **raw**. Get that backwards and match quality quietly collapses instead of erroring.

Every rule here is quoted from Meta's docs rather than recalled — including the five published hash vectors that prove a plausible `replace(/[^a-z]/g,'')` normalizer hashes the empty string for a name like `정`. Ships a **linter** that catches inverted hashing, fabricated `fbc`, and missing `action_source`/`event_id`.

Four reference files + bundled tooling. → [Full details](skills/meta-conversions-api)
Distilled from Meta's [Conversions API documentation](https://developers.facebook.com/documentation/ads-commerce/conversions-api). Unofficial; not affiliated with Meta.

### [`gtm-ga4-meta-tracking`](skills/gtm-ga4-meta-tracking) — one dataLayer, GA4 and Meta both fed correctly

The whole stack fails silently. A `crypto.randomUUID()` `event_id` means the Pixel and CAPI never dedup, so every conversion counts twice. An `ecommerce` object not nulled between pushes bleeds the last event's items into this one, and the totals stay plausible. Pre-hashing email in the dataLayer feels like the careful thing to do and silently kills Enhanced Conversions. None of it throws.

Covers the layer around the tags: dataLayer schema, GTM variables and triggers, GA4's ecommerce spec and its non-retroactive custom-dimension quotas, server-side GTM, and Consent Mode v2. Ships a **linter** — which documents its own blind spot: it can't follow an `event_id` across a network boundary, so a clean run is not evidence of dedup.

Six reference files + bundled tooling. → [Full details](skills/gtm-ga4-meta-tracking)

### [`analytics-js`](skills/analytics-js) — vendor-agnostic analytics that delivers its events

A plugin factory registered uninvoked. An enricher listed after the provider it enriches. A script-loading plugin with no `loaded()`. An `abort()` that isn't returned. Every one of these builds, runs, reviews clean — and quietly drops events. **Three of the four appear in analytics-js's own docs**, so an agent copying from them reproduces the bugs faithfully.

This skill treats the plugins array as a **pipeline** — order is semantics, not style — and ships a **linter** validated against 145 code samples from the official documentation. Zero dependencies, CI-ready.

Six reference files + bundled tooling. → [Full details](skills/analytics-js)
Distilled from [getanalytics.io](https://getanalytics.io); `analytics` is by [David Wells](https://github.com/DavidWells/analytics) (MIT).

---

## Install

```bash
# the whole collection
npx skills add ketanip/agent-skills

# or pick one
npx skills add ketanip/agent-skills --skill nestjs-prisma-rest-superpowers
npx skills add ketanip/agent-skills --skill meta-pixel
npx skills add ketanip/agent-skills --skill meta-conversions-api
npx skills add ketanip/agent-skills --skill gtm-ga4-meta-tracking
npx skills add ketanip/agent-skills --skill analytics-js
```

Taking the whole collection costs you nothing: skills are **inert until relevant**. The NestJS playbook doesn't touch your context while you're wiring up a pixel, and vice versa.

Prefer to vendor by hand? Copy any folder from `skills/` into your project's `.claude/skills/`, or into `~/.claude/skills/` to have it everywhere.

---

## What makes these different from a prompt you paste in

**They load themselves.** The `description` field is a trigger, not documentation. You ask for what you want in plain language; the agent decides a skill is relevant and reads it. You never say "use the skill."

**They're progressive.** A short `SKILL.md` routes to a reference file only when the task actually needs it. Asking for a purchase event doesn't drag the Collaborative Ads spec into your context window.

**They ship tooling, not just prose.** Where a rule can be checked by a machine, it is — `meta-pixel` includes a linter rather than trusting anyone (agent or human) to remember six formatting rules under deadline.

**They admit what they don't know.** A skill that tells your agent to declare victory without verifying is worse than no skill. These say when a result is unverified, and what to check.

---

## Contributing

Found a gap? Have a pattern that belongs here? Open an issue or PR.

New skills welcome — the bar is that it encodes something non-obvious that a competent agent gets *wrong* by default. If the agent already does it right without the skill, the skill is just tokens.

---

## License

MIT © [Ketan Iralepatil](https://github.com/ketanip)

The `meta-pixel` skill is derived from Meta's public [Meta Pixel documentation](https://developers.facebook.com/documentation/meta-pixel) and is not affiliated with or endorsed by Meta.
