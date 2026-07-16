---
name: meta-conversions-api
description: Use when implementing, reviewing, or debugging server-side conversion tracking for Meta ads — the Conversions API (CAPI), POSTs to graph.facebook.com/{pixel_id}/events, user_data or custom_data parameters, hashed customer information (em/ph/fn/external_id), fbc/fbp click and browser IDs, event_id deduplication between the browser Pixel and the server, Event Match Quality (EMQ), the Dataset Quality API, Events Manager access tokens, test_event_code, or app_data/extinfo. Also use when the user asks to "send purchases/leads/signups to Facebook from our backend" without naming the API, when sending conversions from a webhook or queue worker, and when a CAPI integration returns 200 with events_received:1 but conversions are unattributed, double-counted, or match quality is low.
---

# Meta Conversions API

The Conversions API sends conversion events from your server to Meta with a `POST` to
`https://graph.facebook.com/{API_VERSION}/{PIXEL_ID}/events`. Same pixel ID as the browser, same
processing once received — Meta's docs describe the browser Pixel as airmail and server events as
freight: two ways to move the same package to the same address.

**This skill owns the server-side layer.** The browser `fbq()` layer — base code, `track` vs
`trackSingle`, advanced matching in the browser — belongs to the `meta-pixel` skill. The one place
they meet is deduplication, covered below.

## Why this needs care

CAPI accepts a lot of wrong things without complaining. It returns `2xx` when the payload is *valid*
— not when it is *useful*:

```json
{"events_received": 1, "messages": [], "fbtrace_id": "A8s..."}
```

That response is compatible with an event that will never match a human being. A SHA-256 of an
un-normalized email is still a well-formed 64-char hex string. A hashed `fbp` is still a string.
Meta takes them, reports `events_received: 1`, and matches nothing. The failure surfaces weeks later
as low Event Match Quality and unattributed conversions — never as an error.

So the correctness bar here is not "the request succeeded." It's "every field was normalized and
hashed exactly the way the docs specify."

## Start here: what is being asked?

| Situation | Go to |
|---|---|
| Build a payload / send an event from a backend | [The payload](#the-payload) |
| Which fields are required, optional, hashed | `references/parameters.md` |
| Normalize + hash `em`/`ph`/`fn`/`zp`/… | [Hashing](#hashing-is-the-trap) → `references/normalization.md` |
| Get `fbc` from `fbclid`, or handle a missing `_fbc` cookie | `references/normalization.md` → fbc/fbp |
| Pixel and server both fire — avoid double-counting | [Deduplication](#deduplication-against-the-pixel) |
| Match quality is low / improve EMQ | `references/dedup-and-emq.md` |
| 4xx, dropped events, retries, batching | `references/troubleshooting.md` |
| Browser-side `fbq()` work | the `meta-pixel` skill — not this one |
| App events (`app_data`, `extinfo`), offline, business messaging | `references/parameters.md` → beyond web |

## The payload

Every event needs **`event_name`**, **`event_time`**, **`user_data`**, and **`action_source`**.
Website events additionally require **`client_user_agent`** and **`event_source_url`**; non-web
events require only `action_source`.

```json
{
  "data": [{
    "event_name": "Purchase",
    "event_time": 1633552688,
    "event_id": "order-10432",
    "event_source_url": "https://jaspers-market.com/checkout/complete",
    "action_source": "website",
    "user_data": {
      "em": ["309a0a5c3e211326ae75ca18196d301a9bdbd1a882a4d2569511033da23f0abd"],
      "ph": ["254aa248acb47dd654ca3ea53f48c2c26d641d23d7e2e93a1ec56258df7674c4"],
      "client_ip_address": "192.19.9.9",
      "client_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
      "fbc": "fb.1.1554763741205.AbCdEfGhIjKlMnOpQrStUvWxYz1234567890",
      "fbp": "fb.1.1558571054389.1098115397"
    },
    "custom_data": {
      "value": 100.2,
      "currency": "USD",
      "content_type": "product",
      "contents": [{"id": "product.id.123", "quantity": 1}]
    }
  }]
}
```

Send `access_token` as a query parameter or body field. For a **direct** integration you generate it
in Events Manager → your Pixel → Settings → Generate access token; the docs are explicit that *"Your
app does not need to go through App Review. You do not need to request any permissions."* The
`ads_management` / App Review path applies only to platforms sending on behalf of clients
(`references/parameters.md`).

`action_source` is not decoration — it is a factual claim. The docs state that by using the API you
*agree that `action_source` is accurate to the best of your knowledge*. Values: `website`, `email`,
`app`, `phone_call`, `chat`, `physical_store`, `system_generated`, `business_messaging`, `other`.

### `event_time` is the transaction time, not the upload time

This is the most common thing to get subtly wrong: writing `Date.now()/1000` or `time.time()` at the
moment you happen to send. That is the *upload* time. `event_time` means when the conversion actually
happened, as a Unix timestamp in seconds, in GMT.

It matters because the window is enforced and unforgiving: `event_time` may be **up to 7 days**
before you send it, and *"if any `event_time` in `data` is greater than 7 days in the past, we return
an error for the entire request and process no events"* — one stale event in a batch of 1,000 kills
all 1,000. (Offline/`physical_store` events: upload within 62 days.)

If the send is deferred — a queue, a webhook, a retried job — pass the stored `paid_at` through
rather than recomputing a timestamp inside the worker. Meta also scores *event freshness*, so send as
close to real time as you can while keeping `event_time` truthful.

## Hashing is the trap

Unlike the browser Pixel, **CAPI does not hash for you.** You normalize, then SHA-256, then send hex.
Two rules, and mixing them up is the single highest-cost mistake on this API:

- **Customer information must be normalized and hashed:** `em`, `ph`, `fn`, `ln`, `ge`, `db`, `ct`,
  `st`, `zp`, `country`. (`external_id` — hashing *recommended*, consistency across channels
  mandatory.)
- **These must NOT be hashed, ever:** `client_ip_address`, `client_user_agent`, `fbc`, `fbp`,
  `subscription_id`, `fb_login_id`, `lead_id`, `page_id`, `ctwa_clid`, and the rest of the
  do-not-hash list in `references/parameters.md`.

Hashing `fbc` destroys the click ID that ties the conversion to the ad — the strongest attribution
signal you have — and returns `200 events_received: 1` while doing it. Nothing tells you.

**Normalization is not "trim and lowercase."** Each field has its own rule, and a plausible-looking
regex will silently delete data. Meta publishes exact vectors; these are real and verified:

| Input | Normalized | SHA-256 |
|---|---|---|
| `John_Smith@gmail.com` | `john_smith@gmail.com` | `62a14e44f765419d…` |
| `(650)555-1212` (US) | `16505551212` | `e323ec626319ca94…` |
| `정` | `정` (UTF-8, **not** stripped) | `8fa8cd9c440be61d…` |
| `Valéry` | `valéry` (accent kept) | `08e1996b5dd49e62…` |
| `2/16/1997` | `19970216` | `01acdbf6ec7b4f47…` |
| `United States` | `us` | `79adb2a2fce5c6ba…` |

`[^a-z]`-style scrubbing turns `정` into an empty string and hashes *that*. Zip truncation to 5 chars
is a **US-only** rule — applying it globally mangles UK postcodes. Full rules and full digests:
`references/normalization.md`. Never hash an empty string; omit the field instead.

## Deduplication against the Pixel

Running CAPI alongside the Pixel is the recommended "redundant setup" — but only if you deduplicate,
or you double-count every conversion.

Send the **same `event_id`** from both sides, with the same `event_name`:

```js
fbq('track', 'Purchase', {value: 12, currency: 'USD'}, {eventID: 'order-10432'});  // browser
```
```json
{"event_name": "Purchase", "event_id": "order-10432"}
```

An order or transaction ID is the natural choice — it's stable across retries and genuinely unique
per conversion. The rules that bite: dedup only applies **within 48 hours** of the first event with
that `event_id`, and if browser and server arrive within ~5 minutes of each other Meta favors the
browser event. `event_id` is marked *optional* in the reference table and is effectively required for
any redundant setup. Details, plus the `fbp`/`external_id` fallback method and its limitations, in
`references/dedup-and-emq.md`.

## Verify before you call it done

A diff that looks right is exactly the failure mode here, because nothing errors.

1. Run `python3 scripts/check_capi.py <paths>` — it flags inverted hashing, fabricated `fbc`, missing
   `action_source`/`event_id`, `sha256("")`, and the malformed-value patterns above. It reads source
   text; it cannot tell you an event matched a user.
2. Send with `test_event_code` (from Events Manager → Test Events) and watch it arrive. Remove it
   from production payloads.
3. Check Events Manager → Overview within ~20 minutes: raw vs matched vs attributed, and Event Match
   Quality. Meta suggests aiming for **EMQ ≥ 6.0**.

If the user can't do steps 2–3, say plainly that the integration is unverified and what to look for.
Do not report a `200` as proof it works — that is the exact inference this API punishes.

## Reference files

- `references/parameters.md` — full field matrix: main body, server event, `user_data` hash/no-hash,
  `custom_data` standard parameters, `app_data`/`extinfo`, `original_event_data`, LDU.
- `references/normalization.md` — per-field normalization rules with Meta's verified SHA-256 vectors;
  `fbc`/`fbp` construction from `fbclid`; `external_id` consistency.
- `references/dedup-and-emq.md` — both dedup methods, the 48-hour window, EMQ and the Dataset Quality
  API.
- `references/troubleshooting.md` — what 2xx/4xx mean, retries, timeouts, batching, and what the docs
  do *not* say about error codes.

## Attribution

Distilled from Meta's official Conversions API documentation:
[Conversions API](https://developers.facebook.com/documentation/ads-commerce/conversions-api) —
[Using the API](https://developers.facebook.com/documentation/ads-commerce/conversions-api/using-the-api),
[Parameters](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters),
[Customer Information Parameters](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/customer-information-parameters),
[fbp and fbc](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/fbp-and-fbc),
[Deduplication](https://developers.facebook.com/documentation/ads-commerce/conversions-api/deduplicate-pixel-and-server-events),
[Dataset Quality API](https://developers.facebook.com/documentation/ads-commerce/conversions-api/dataset-quality-api),
[Troubleshooting](https://developers.facebook.com/documentation/ads-commerce/conversions-api/support).

This is an **unofficial, independent distillation** — not affiliated with or endorsed by Meta. "Meta",
"Facebook", and "Conversions API" are trademarks of Meta Platforms, Inc. Meta changes parameters and
validation rules without notice: **re-verify against the canonical source before implementing.**
