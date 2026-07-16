---
name: gtm-ga4-meta-tracking
description: Implement, debug, and verify tracking that flows through Google Tag Manager into GA4 and Meta (Pixel + Conversions API) — dataLayer schema, GTM variables/triggers/tags, GA4 events and ecommerce items[], server-side GTM, Pixel↔CAPI event_id deduplication, Advanced Matching / Enhanced Conversions hashing, and Consent Mode v2. Use whenever the user mentions GTM, Google Tag Manager, dataLayer, GA4, gtag, Measurement Protocol, sGTM, Stape, Conversions API, CAPI, event_id dedup, Event Match Quality, Consent Mode, or fbp/fbc — and when they ask to "track purchases/leads/signups", "send ecommerce events to GA4 and Facebook", "set up server-side tracking", "improve match quality", or "stop double-counting conversions", even if they name no product. Also use when reviewing an existing container or dataLayer, since mismatched event IDs, wrong-side hashing, and unregistered parameters all fail silently.
---

# GTM → GA4 + Meta

GTM is a **transport-and-transform layer, not a data source**. The page pushes a plain object onto `window.dataLayer`; GTM reads it with variables, matches it with triggers, and fans it out to tags. GA4 and Meta then each want that same event in their own shape — different names, different parameter keys, different rules about who hashes what.

Everything in this stack fails silently. There is no validation step anywhere in it. A mismatched `event_id` between Pixel and CAPI doesn't error — it just double-counts every conversion. Pre-hashed email in the dataLayer doesn't error — Enhanced Conversions just receives nothing, forever. `content_ids: [1234]` where the catalog holds `'1234'` doesn't error — dynamic ads just never match. A custom parameter you never registered as a custom dimension doesn't error — it's simply absent from every report, and not retroactively fixable. You find out from a revenue meeting, not a stack trace.

**Scope note:** browser `fbq()` parameter shape (value/currency/contents/content_type formatting, multi-pixel `trackSingle`) belongs to the **`meta-pixel`** skill — use it for that and don't duplicate it here. This skill owns everything around it: the dataLayer, the container, GA4, the server side, dedup, and consent.

## Start here: what is being asked?

| Situation | Go to |
|---|---|
| Design the dataLayer / what to push | [The canonical push](#the-canonical-push) + `references/datalayer-schema.md` |
| Pixel and CAPI both firing — dedup | [The dedup contract](#the-dedup-contract-event_id) — **the most common break** |
| Attach email/phone for match rates | [The hashing boundary](#the-hashing-boundary) — who hashes where |
| Which GA4 event / what params / items[] | `references/ga4-events-and-limits.md` |
| Custom params missing from GA4 reports | `references/ga4-events-and-limits.md` → custom dimensions |
| Build the CAPI server payload | `references/meta-capi.md` |
| Server-side GTM, sGTM, FPID, Stape | `references/server-side-gtm.md` |
| GTM variables, triggers, built-ins | `references/gtm-container-config.md` |
| Consent Mode v2, GDPR, LDU, sensitive data | `references/consent-and-privacy.md` |
| Nothing shows up / double counting | [Verify](#verify-before-you-call-it-done) |

## The dedup contract (`event_id`)

Running Pixel **and** CAPI is correct — that's the redundancy. Meta collapses the pair when **`event_name` AND `event_id` both match**, within a **48-hour** window. Miss either and you don't get an error, a warning, or a duplicate badge. You get two conversions, inflated ROAS, and a bidding algorithm optimizing against a number that is twice reality.

So `event_id` has exactly one rule, and it is about **provenance, not format**:

> The browser and the server must *derive* the same ID from shared state. They must never each *generate* one.

```js
// ❌ the failure. Nothing here is wrong-looking, and it is 100% broken.
event_id: crypto.randomUUID()      // browser makes one...
event_id: uuidv4()                 // ...server makes a different one. No dedup, ever.

// ✅ derive from something both sides already know
event_id: `purchase.${order.id}`   // order id — both sides have it
```

For `purchase` this is easy and agents usually get it right: the order ID is shared. **The failure is on every other event.** `Lead`, `CompleteRegistration`, `AddToCart` have no natural shared key, so a random UUID gets used, and the moment anyone adds a server-side counterpart the double-counting starts silently.

If there is no natural shared key, the browser must **mint the ID and hand it to the server** in the same request that triggers the server event:

```js
const eventId = crypto.randomUUID();          // minted ONCE, in one place
dataLayer.push({ event: 'sign_up', event_id: eventId, /* ... */ });
await api.signup({ ...values, event_id: eventId });   // travels with the payload
```

The server then reuses that exact string — it does not make its own. If you cannot get the ID across the boundary, you do not have dedup; send **one** side only, rather than both and hope.

## The hashing boundary

This is where implementations quietly lose their identity data, and it breaks in **both** directions. The destinations do not agree with each other:

| Destination | What it wants | Who hashes |
|---|---|---|
| **dataLayer** | **plaintext** | nobody — it's just carrying it |
| GA4 User-Provided Data (Enhanced Conversions) | **plaintext** | Google's tag, at send time |
| Meta **browser** Pixel Advanced Matching | **plaintext** | `fbevents.js`, at send time |
| Meta **CAPI** (server) | **SHA-256 hex, pre-normalized** | **you**, before the request |
| `fbp` / `fbc` / `client_ip_address` / `client_user_agent` | raw | **never hash these** |

The instinct "raw PII must never touch the dataLayer, so I'll hash it in the browser first" is a reasonable-sounding privacy reflex, and it **silently disables Enhanced Conversions** — the GA4 UPD variable takes plaintext and hashes it itself; hand it a 64-char hex digest and it has no idea what to do with it. Nothing errors. The channel is just dead.

Hash **only** at the server boundary, and normalize before you hash — an un-normalized hash is a *wrong* hash, not a weaker one, because `" Ann@X.com"` and `"ann@x.com"` produce completely unrelated digests:

```js
em: sha256(email.trim().toLowerCase())              // gmail: also strip dots + '+' suffix
ph: sha256(phone.replace(/\D/g, ''))                // digits only, country code, no '+'
fbp: cookie('_fbp'),                                 // raw. hashing it destroys it.
client_ip_address: req.ip,                           // raw.
```

If the dataLayer genuinely must not carry plaintext (a real constraint on some sites), the answer is to keep identity **out of the container entirely** and send it server-side from your own backend — not to pre-hash and pretend the browser tags can still use it. Full field list and normalization rules: `references/meta-capi.md`.

## The canonical push

One schema feeds both vendors. GA4's ecommerce shape is the source of truth; the Meta tag maps out of it.

```js
dataLayer.push({ ecommerce: null });        // ALWAYS first — see below
dataLayer.push({
  event: 'purchase',
  event_id: 'purchase.10057',               // shared with Pixel + CAPI
  user_data: {                              // plaintext; tags hash at send time
    email: 'jane@example.com',
    phone_number: '+14155551234'
  },
  ecommerce: {
    transaction_id: '10057',
    currency: 'USD',                        // ISO 4217 code, not '$'
    value: 129.97,                          // number, not a string
    tax: 8.20, shipping: 5.00, coupon: 'SUMMER',
    items: [
      { item_id: 'SKU_4001', item_name: 'Blue T-Shirt', price: 29.99, quantity: 1, index: 0 }
    ]
  }
});
```

**`dataLayer.push({ ecommerce: null })` before every ecommerce push.** GTM's data model *persists* across pushes — it merges, it does not replace. Skip the null and the previous event's `items` bleed into this one: your `purchase` ships the cart's `add_to_cart` items alongside its own, and the numbers stay plausible enough that nobody notices. (Pushing `undefined` does not clear it. Use `null`.)

**Type discipline is load-bearing at the boundary.** `content_ids` and `contents[].id` must match the catalog's product IDs *exactly*, including type — `[1234]` will not match `'1234'`. The half-fix is the common one: normalizing `contents[].id` with `String()` while leaving `content_ids` raw. Normalize both, in one place:

```js
function () {                                        // GTM Custom JavaScript variable
  var items = {{dlv - ecommerce.items}} || [];
  return items.map(function (i) { return String(i.item_id); });   // String() — always
}
```

The full `dataLayer` → GA4 → Meta mapping table (every key, both directions) is in `references/datalayer-schema.md`.

## The parameter you send is not the parameter you can report on

GA4 accepts any custom parameter you send and stores it. It will not appear in a single report until you **register it as a custom dimension** — and registration is **not retroactive**, so the data you collected before registering is unreachable forever. Takes 24–48h to populate.

This one costs weeks because the implementation looks complete: the event fires, DebugView shows the parameter, and the report is empty. Register as you instrument, and mind the quotas — **50 event-scoped / 25 user-scoped / 10 item-scoped** on a standard property, with a 48-hour wait before a deleted one can be re-added. Budget them; don't register high-cardinality values you'll never segment by.

Other limits that bite: **25 parameters per event** (automatic ones count), **100 characters** per parameter value (`page_location` 1,000), 40-char event names. See `references/ga4-events-and-limits.md`.

## Consent gates the tag, not just the cookie

Set all four Consent Mode v2 signals to `denied` **before the GTM container loads** — a tag that fires before the default is set has already happened, and there is no undo. Details, Basic vs Advanced, and the legal surface: `references/consent-and-privacy.md`.

The failure worth calling out here, because it survives every browser-side test: **CAPI bypasses the browser, so it bypasses your consent gate.** Your webhook fires hours later with no browser to ask. Persist the consent state on the order/user record at collection time and check it server-side before dispatching:

```js
if (order.consent?.ad_user_data !== 'granted') return;   // do not send to Meta
```

Hashing is pseudonymization, not anonymization — a hashed email is still personal data. Moving a call server-side changes the transport, not the lawful basis.

## Verify before you call it done

Nothing in this stack throws, so "the diff looks right" is not evidence. Three checks, in order:

1. **Run the linter** — `python scripts/check_tracking.py <paths>`. It flags randomly-generated `event_id`s, ecommerce pushes with no preceding `ecommerce: null`, non-string `content_ids`, pre-hashed PII in the dataLayer, hashed `fbp`/`fbc`, plaintext email in a CAPI `user_data`, `value`/`currency` type errors, over-long GA4 event names, and `num_items` outside `InitiateCheckout`.

   **Know what it cannot see.** It catches `event_id: crypto.randomUUID()` written *inline*, because that's mechanically wrong every time. It **cannot** catch `const id = crypto.randomUUID()` that is minted and then never handed to the server — that's the mint-and-pass pattern when the ID crosses the boundary, and the exact failure when it doesn't. Same code, different fate, decided by a request body the linter can't follow. **A green run is not evidence of dedup.** Only step 3 is.
2. **Watch it fire.** GTM Preview/Tag Assistant for triggers and variables (check the Consent tab); GA4 DebugView for parameters; Meta **Test Events** for the payload.
3. **Confirm dedup specifically.** In Events Manager, a working pair shows **one event from two sources**. Two separate rows means your `event_id`s don't match — that is the whole ballgame, and it is invisible everywhere else. Then check Event Match Quality on `Purchase`; if it's low, `fbc`/`fbp` are almost certainly not reaching the server.

If you can't run 2 and 3, say the implementation is unverified and name what to look for. Don't declare victory on a linter pass.

## Reference files

- `references/datalayer-schema.md` — the canonical full-funnel dataLayer schema and the complete dataLayer → GA4 → Meta mapping table.
- `references/ga4-events-and-limits.md` — automatic/enhanced-measurement/recommended events, the full ecommerce spec and `items[]` fields, identifiers, custom dimensions, every limit and quota, Measurement Protocol, BigQuery export, and the PII policy.
- `references/meta-capi.md` — server event fields, `user_data` and normalization, `custom_data`, `fbp`/`fbc` structure, dedup mechanics, Event Match Quality, LDU.
- `references/server-side-gtm.md` — sGTM clients and the event data model, FPID/FPLC, the dual-dispatch GA4 + CAPI architecture, enrichment and transformations, hosting.
- `references/gtm-container-config.md` — variable types, the ~44 built-in variables, trigger types and their dataLayer events.
- `references/consent-and-privacy.md` — Consent Mode v2, GDPR/ePrivacy, US state laws and LDU, sensitive-category restrictions, and the legal caveats.

## Attribution & source of truth

This skill is distilled from a **research report generated by a Claude research session (Anthropic)** that synthesized Google's and Meta's public developer documentation together with practitioner sources, current as of **July 2026**. It is **not** vendor documentation, and it is neither affiliated with nor endorsed by Google or Meta. Trademarks belong to their owners.

Primary sources, which win whenever they disagree with this skill:

- [GA4 developer docs](https://developers.google.com/analytics/devguides/collection/ga4)
- [Google Tag Manager docs](https://developers.google.com/tag-platform/tag-manager)
- [Meta Pixel docs](https://developers.facebook.com/docs/meta-pixel)
- [Meta Conversions API docs](https://developers.facebook.com/documentation/ads-commerce/conversions-api)

**Caveats, carried forward from the source report:**

- **Vendor docs change without notice.** Parameter lists, limits, and enforcement dates were verified as of mid-2026; Meta in particular changes CAPI parameters and validation rules silently. Re-verify against the primary sources before implementing.
- **Several widely-cited figures are vendor-marketing or practitioner estimates, not official.** Consent Mode recovery rates (15–25%, or Google's ~70% claim), per-parameter EMQ uplift ("+4 for email"), and CIPA claim counts come from vendor marketing, law-firm trackers, and blogs — Google and Meta do not publish exact figures. This skill omits them from guidance rather than dressing them up as specifications; where a number appears in `references/consent-and-privacy.md`, it is labeled.
- **Legal status is unsettled and jurisdiction-specific**, and **nothing here is legal advice.** Engage privacy counsel for your verticals and jurisdictions.
