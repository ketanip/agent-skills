# meta-conversions-api

> Server-side Meta conversion tracking that actually matches a human being — correct normalization, correct hashing, correct dedup, verified. Because CAPI returns `200 events_received: 1` for events that will never match anyone.

```bash
npx skills add ketanip/agent-skills --skill meta-conversions-api
```

> Part of the [ketanip/agent-skills](https://github.com/ketanip/agent-skills) collection — drop `--skill meta-conversions-api` to install every skill in it. Works with Claude Code, Cursor, Copilot, Windsurf, Cline — any agent that supports [skills.sh](https://skills.sh).

---

## The response that means nothing

```json
{"events_received": 1, "messages": [], "fbtrace_id": "A8s..."}
```

Your CI is green. The request succeeded. The event will never be attributed to anyone.

Meta's docs are precise about this and everyone reads past it: a `2xx` is returned *"if the event payload is valid."* Valid — not useful. A SHA-256 of an un-normalized email is a perfectly well-formed 64-character hex string. So is a SHA-256 of `fbp`, which was never supposed to be hashed at all. CAPI accepts both, counts them, and matches nobody.

There is no error. No warning. Nothing red. You find out six weeks later, when someone notices Event Match Quality sitting at 3.

---

## The inversion

The Pixel hashes for you. **CAPI does not.** And the fields split into two lists that must never touch:

```js
user_data: {
  em: sha256(normalizeEmail(email)),   // hash — required
  ph: sha256(normalizePhone(phone)),   // hash — required
  fbp: req.cookies._fbp,               // NEVER hash
  fbc: req.cookies._fbc,               // NEVER hash
  client_ip_address: req.ip,           // NEVER hash — docs: "must never be hashed"
  client_user_agent: req.get('ua'),    // NEVER hash
}
```

Hash the bottom four and you've destroyed the click ID that ties the conversion to the ad — the strongest attribution signal in the payload. Status code: 200.

**And normalization is not "trim and lowercase."** This is the part that survives code review, because it looks like diligence:

```js
const normName = (n) => n.trim().toLowerCase().replace(/[^a-z]/g, '');
```

Meta's own published test vector is the Korean name `정`. That regex turns it into `""`, hashes the empty string, and ships a constant digest that matches every other advertiser who made the same mistake. `Valéry` becomes `valry`. Meta publishes exact SHA-256 vectors for both — [this skill verifies against all seven](references/normalization.md).

Same shape, different field: `zip.slice(0, 5)` is a **US-only** rule. Applied globally it mangles every UK postcode you have.

---

## What the skill does about it

It treats **the 200 as meaningless** and the normalization vectors as the specification — then ships a linter so the mechanical half isn't a matter of anyone's attention at 6pm.

```bash
python3 skills/meta-conversions-api/scripts/check_capi.py src/
```

```
ERROR src/capi.js:8:  `fbp` is hashed but must be sent raw. fbp is the browser ID used for
                      cross-session identity and as a dedup/external-id fallback. The API still
                      returns 200 events_received:1 -- it just never matches.
ERROR src/capi.js:9:  fabricated `fbc` value ending in 'unknown'. A synthesized click ID cannot
                      match and invents an ad-click attribution record for organic/direct
                      conversions. If there is no _fbc cookie and no fbclid, omit fbc entirely.
ERROR src/capi.js:6:  `em` appears to be assigned an unhashed value (`req.body.email`). Meta
                      requires SHA-256 of the *normalized* value.
ERROR src/capi.js:3:  payload builds an event but never sets `action_source` -- a required
                      parameter for every Conversions API event.
ERROR src/norm.js:3:  normalizer strips every non-a-z character. Meta's own published vectors
                      include the name 'jeong' (Korean) and 'Valery' (accented) -- special
                      characters must be kept and UTF-8 encoded, not removed.
WARN  src/capi.js:4:  no `event_id` set. If the browser Pixel also fires this event, every
                      conversion is counted twice.
INFO  src/capi.js:5:  `event_time` is computed from the current clock -- that is the upload time.
```

Zero dependencies, `python3` only, exit code `1` on errors — drops into a pre-commit hook or CI step. Run `--self-test` to see it prove itself. Useful on its own even if you never install the skill.

---

## The traps, and why they survive review

**`event_time` is the transaction time, not the upload time.** `Date.now()/1000` is right up until the send is deferred — a queue, a webhook, a retry — and then it's a lie. The window is 7 days and it's enforced brutally: *"if any `event_time` in `data` is greater than 7 days in the past, we return an error for the entire request and process no events."* One stale event kills a batch of 1,000.

**A mismatched `event_id` means no dedup.** Not an error — double-counted revenue. Both channels must send the same ID *and* the same event name, within 48 hours. Generating a UUID independently on each side is the classic version of this bug.

**Don't invent an `fbc`.** `` `fb.1.${Date.now()}.unknown` `` is not a click ID. It can't match, and it manufactures a fake ad-click record for every organic conversion. No cookie and no `fbclid` → omit the field.

**IP and user agent must come from the customer's request.** Fire CAPI from a Stripe webhook and you're sending your worker's IP and your HTTP client's user agent. Worse than sending nothing. Capture at checkout, persist on the order, pass into the job.

**`event_source_url` is not the referrer.** The referrer has its own parameter, `referrer_url`.

**A direct integration needs no App Review and no permissions** — the docs say so explicitly. The `ads_management` + App Review path is only for platforms sending on behalf of clients. Plenty of implementations burn a week on this.

**`test_event_code` is not a sandbox.** *"Events sent with `test_event_code` are not dropped."* They flow into Events Manager and are used for targeting and measurement. It must come out of production payloads.

---

## What your agent learns

| Reference | What it covers |
|---|---|
| **SKILL.md** | Decision table → payload → hashing → dedup → verify. Routes to a reference only when the task needs one. |
| **parameters.md** | Full field matrix: main body, server event, the `user_data` hash/do-not-hash split, `custom_data` standard parameters, `app_data`/`extinfo` positional array, `original_event_data`, LDU, access tokens, versioning |
| **normalization.md** | Per-field rules with Meta's seven published SHA-256 vectors as test fixtures; `fbc`/`fbp` construction from `fbclid`; `external_id` cross-channel consistency; where IP/UA must come from |
| **dedup-and-emq.md** | Both dedup methods and their windows, the `fbp`/`external_id` fallback's asymmetric limits, EMQ, the Dataset Quality API, raising EMQ in order of leverage |
| **troubleshooting.md** | What 2xx/4xx actually mean, the 1500 ms timeout, retry rules, all-or-nothing batching, Test Events, and a diagnostic ladder |

Loaded on demand. Asking for a Purchase event doesn't drag the `extinfo` array into your context.

**Scope:** this skill owns the server-side layer. The browser `fbq()` layer — base code, `trackSingle`, advanced matching — belongs to the companion [`meta-pixel`](../meta-pixel) skill. The two meet at deduplication.

---

## Just talk to your agent normally

**"Send purchases to Facebook from our Django backend"**
→ Normalized-then-hashed `user_data`, raw `fbp`/`fbc`/IP/UA, `action_source`, `event_id` from the order ID — plus a note that the pixel needs the matching `eventID`.

**"Our match quality is low"**
→ Checks normalization against Meta's vectors *before* suggesting more fields, because a wrongly-normalized `em` scores like a missing one.

**"We're sending CAPI from our Stripe webhook"**
→ Flags that there's no customer request in scope, so IP/UA/`fbp`/`fbc` would be your server's — capture at checkout and pass through, with the real `event_time`.

**"Why are our purchases double-counted?"**
→ Event Deduplication tab, the Overlap metric, and the 48-hour window — not a guess about the payload.

---

## Honest limits

- The linter is **static analysis over source text**. It cannot tell you whether an event matched a user — nothing can except Events Manager. The skill says so too, rather than letting your agent declare victory on a 200.
- **It can't verify normalization at runtime**, only spot regexes that are wrong by inspection. Meta's seven vectors are in `normalization.md`; make them unit tests.
- **Meta's docs do not publish a table of CAPI ingestion error codes.** They say `4xx` with *"minimal error details."* This skill says that plainly instead of reciting error codes from memory — if you've seen a code quoted elsewhere, it didn't come from here.
- Where the docs are silent — whether a stringified `value` is accepted, the current `user_data` combination requirements added in v13.0 — the skill says *silent*, and points at the canonical page.

---

## Attribution

Distilled from Meta's official Conversions API documentation:

- [Conversions API](https://developers.facebook.com/documentation/ads-commerce/conversions-api) — overview
- [Using the API](https://developers.facebook.com/documentation/ads-commerce/conversions-api/using-the-api) — requests, batching, `event_time`, Test Events, limits
- [Parameters](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters) — [server event](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/server-event), [customer information](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/customer-information-parameters), [custom data](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/custom-data), [app data](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/app-data), [fbp and fbc](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/fbp-and-fbc), [external ID](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/external-id)
- [Deduplication](https://developers.facebook.com/documentation/ads-commerce/conversions-api/deduplicate-pixel-and-server-events)
- [Verifying Your Setup](https://developers.facebook.com/documentation/ads-commerce/conversions-api/verifying-setup) and the [Dataset Quality API](https://developers.facebook.com/documentation/ads-commerce/conversions-api/dataset-quality-api)
- [Troubleshooting](https://developers.facebook.com/documentation/ads-commerce/conversions-api/support) and the [Payload Helper](https://developers.facebook.com/documentation/ads-commerce/conversions-api/payload-helper)

This skill is an **unofficial, independent distillation** of that public documentation into a form an AI coding agent loads on demand. It is **not affiliated with, authorized by, or endorsed by Meta**. "Meta", "Facebook", "Meta Pixel", and "Conversions API" are trademarks of **Meta Platforms, Inc.**

It deliberately does **not** reproduce Meta's documentation wholesale — it is a rewritten distillation that quotes only the load-bearing lines and deep-links the source for everything else. **Meta changes Conversions API parameters and validation rules without notice.** Treat the linked pages as canonical and re-verify before implementing. Any errors here are mine, not Meta's.

---

## Skill details

| | |
|---|---|
| **Skill name** | `meta-conversions-api` |
| **Collection** | [ketanip/agent-skills](https://github.com/ketanip/agent-skills) |
| **Activation** | Automatic on Conversions API, CAPI, server-side conversion tracking, event match quality, pixel/server dedup, and general "send conversions to Facebook from our backend" work |
| **Companion** | [`meta-pixel`](../meta-pixel) — the browser `fbq()` layer |
| **Reference files** | 4 focused files, loaded on demand |
| **Bundled tooling** | `check_capi.py` payload linter (zero dependencies, CI-ready, `--self-test`) |
| **Author** | [Ketan Iralepatil](https://github.com/ketanip) |
