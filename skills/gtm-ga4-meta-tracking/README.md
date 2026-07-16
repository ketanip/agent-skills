# gtm-ga4-meta-tracking

> Ship GTM tracking that reaches GA4 and Meta intact — one dataLayer, deduplicated conversions, identity hashed on the right side of the wire. Because nothing in this stack validates anything, and a broken container reports beautifully.

```bash
npx skills add ketanip/agent-skills --skill gtm-ga4-meta-tracking
```

> Part of the [ketanip/agent-skills](https://github.com/ketanip/agent-skills) collection — drop `--skill gtm-ga4-meta-tracking` to install every skill in it. Works with Claude Code, Cursor, Copilot, Windsurf, Cline — any agent that supports [skills.sh](https://skills.sh).

---

## The two lines that double your conversions

```js
// browser
event_id: crypto.randomUUID()
```
```js
// server
event_id: uuidv4()
```

Both correct-looking. Both shipped. Meta deduplicates the Pixel against the Conversions API by matching `event_id` **and** `event_name` — so two independently generated IDs mean **no dedup, ever**. Every purchase counts twice. Events Manager shows two healthy sources. Nothing errors, nothing warns, and your ROAS is exactly 2× a lie while the bidding algorithm optimizes against it.

That's one failure. The stack is made of them:

```js
user_data: { em: await sha256(email) }      // dataLayer wants PLAINTEXT — the tags hash.
                                            // Enhanced Conversions now receives nothing. Silently.
content_ids: [1234]                         // catalog holds '1234'. Dynamic ads match zero products.
dataLayer.push({ event: 'purchase', ... })  // no `ecommerce: null` first — GTM MERGES.
                                            // Last event's items ride along. Totals stay plausible.
fbp: sha256(cookie('_fbp'))                 // Meta needs it raw. You just deleted your best match signal.
```

None of these throw. None appear in a code review. You find out from a revenue meeting six weeks later, and by then the data is unrecoverable — GA4 custom dimensions aren't retroactive, so the parameter you forgot to register simply never existed.

---

## We checked, rather than assumed

Before writing a line of this skill, we handed two agents a realistic tracking brief — a Shopify-style ecommerce funnel and a React SaaS lead-gen funnel — with no skill loaded, and read what they produced.

Both wrote confident, well-organized, *plausible* implementations. Both broke in the same places:

- **Both** generated `event_id` randomly for every event except `purchase`. One agent wrote its own escape hatch into a comment — *"a random UUID is fine (client passes it to your API if you also mirror those server-side)"* — and then never passed it.
- **Both** broke the hashing boundary, in **opposite directions**. One pre-hashed email in the browser (*"Raw email/phone must never enter dataLayer"*) — a reasonable-sounding privacy reflex that silently disables GA4 Enhanced Conversions. The other sent plaintext correctly and then never wired the User-Provided Data variable at all. Same dead channel, opposite mistake.
- **One** normalized `contents[].id` with `String()` and left `content_ids` raw — the classic half-fix, where the payload looks right in Test Events and catalog ads still match nothing.
- **Neither** mentioned registering custom dimensions. Both sent custom parameters that would be invisible in every GA4 report, forever, non-retroactively.

Notably, both got **consent** right — defaults before the container, and even the server-side gate. So this skill doesn't belabor consent. It spends its tokens where agents actually fail.

---

## What the skill does about it

It treats **`event_id` provenance and the hashing boundary as the load-bearing parts of the job**, and ships a linter so the mechanical rules are checked by a machine instead of by anyone's vigilance under deadline.

The one rule that matters most, stated so it can't be negotiated with:

> The browser and the server must **derive** the same `event_id` from shared state. They must never each **generate** one.

And the boundary that breaks both ways:

| Destination | Wants | Who hashes |
|---|---|---|
| dataLayer | **plaintext** | nobody |
| GA4 User-Provided Data | **plaintext** | Google's tag, at send time |
| Meta browser Pixel | **plaintext** | `fbevents.js`, at send time |
| Meta CAPI (server) | **SHA-256 hex** | **you** |
| `fbp` / `fbc` / IP / UA | raw | **never** |

```bash
python skills/gtm-ga4-meta-tracking/scripts/check_tracking.py src/
```

```
ERROR src/checkout.js:4: event_id is randomly generated (crypto.randomUUID()) in a dataLayer push
                        -- the browser and server will each produce a different value, so Meta
                        never deduplicates and every conversion double-counts.
ERROR src/checkout.js:4: `em` looks pre-hashed in a dataLayer push. The dataLayer must carry
                        PLAINTEXT: the GA4 User-Provided Data variable and fbevents.js hash at
                        send time. A 64-char digest silently disables Enhanced Conversions.
ERROR src/checkout.js:11: content_ids: [1234, 5678] contains numeric literals. Catalog matching
                        is type-sensitive -- [1234] does not match '1234'.
ERROR src/checkout.js:11: ecommerce push with no preceding `dataLayer.push({ ecommerce: null })`.
                        GTM's model MERGES rather than replaces, so the previous event's items[]
                        bleed into this one. The totals stay plausible, which is why nobody notices.
ERROR src/capi.js:2:    `fbp` is being hashed -- Meta requires it raw.
ERROR index.html:5:     gtag('consent','default',...) appears AFTER the GTM snippet. Tags that
                        fire before the default is set have already fired -- there is no undo.
```

Zero dependencies, plain `python3`, CI-ready. It's a linter, not proof — it can't tell you an event fired, and the skill says so plainly rather than letting your agent declare victory on a green check.

---

## Scope

This skill owns the **GTM / dataLayer / GA4 / server-side / dedup / consent** layer.

Browser `fbq()` parameter shape — `value`/`currency`/`contents` formatting, multi-pixel `trackSingle` — belongs to the [`meta-pixel`](../meta-pixel) skill, which this one cross-references rather than duplicates. Install both if you're doing the whole job.

**Six reference files**, loaded on demand:

| File | Covers |
|---|---|
| `datalayer-schema.md` | The canonical full-funnel schema; the complete dataLayer → GA4 → Meta mapping table |
| `ga4-events-and-limits.md` | Event surface, ecommerce + `items[]` spec, identifiers, every quota, Measurement Protocol, BigQuery, the PII policy |
| `meta-capi.md` | Server event fields, `user_data` + normalization, `fbp`/`fbc`, dedup, Event Match Quality, LDU |
| `server-side-gtm.md` | sGTM clients, FPID/FPLC, dual-dispatch architecture, sGTM vs. your own webhook |
| `gtm-container-config.md` | Variables, the ~44 built-ins, triggers, consent on Custom HTML tags, tag sequencing |
| `consent-and-privacy.md` | Consent Mode v2, GDPR/ePrivacy, US state laws, sensitive categories, legal caveats |

---

## Attribution & honest provenance

This skill is distilled from a **research report generated by a Claude research session (Anthropic)**, which synthesized Google's and Meta's public developer documentation together with practitioner sources, current as of **July 2026**.

**It is not vendor documentation.** It is not affiliated with, endorsed by, or reviewed by Google or Meta. Trademarks belong to their owners.

Primary sources — these win whenever they disagree with the skill:

- [GA4 developer docs](https://developers.google.com/analytics/devguides/collection/ga4)
- [Google Tag Manager docs](https://developers.google.com/tag-platform/tag-manager)
- [Meta Pixel docs](https://developers.facebook.com/docs/meta-pixel)
- [Meta Conversions API docs](https://developers.facebook.com/documentation/ads-commerce/conversions-api)

**Caveats, carried forward from the source report rather than quietly dropped:**

- **Vendor docs change without notice.** Parameter lists, limits, and enforcement dates were verified as of mid-2026. Meta in particular changes CAPI parameters and validation rules silently. Re-verify against the primary sources before implementing.
- **Several widely-repeated figures are marketing or estimates, not specifications.** Consent Mode recovery rates (15–25%, or Google's ~70% claim), per-parameter EMQ uplift ("+4 for email"), and CIPA claim counts come from vendor marketing, law-firm trackers, and practitioner blogs — Google and Meta publish none of them. The skill omits them from guidance and labels them where they appear.
- **Legal status is unsettled and jurisdiction-specific.** The EU-US Data Privacy Framework appeal is pending (CJEU C-703/25 P); CIPA rulings are split. **Nothing in this skill is legal advice** — engage privacy counsel for your verticals and jurisdictions.
- **"Technically possible" ≠ "permitted."** The skill documents the technical surface *and* the policy limits, because the defensible implementation is the data-minimized one, regardless of what the tools would physically allow.

---

## License

MIT © [Ketan Iralepatil](https://github.com/ketanip)
