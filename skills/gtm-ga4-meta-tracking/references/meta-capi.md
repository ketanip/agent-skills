# Meta Conversions API (server-side)

The browser Pixel and the Conversions API are two transports for the same event. Running both is the point — CAPI survives ad blockers, ITP, and the user closing the tab before `fbevents.js` loads. The price of running both is that you must make deduplication work, and nothing tells you when it doesn't.

For browser `fbq()` parameter shape, use the **`meta-pixel`** skill.

This file covers the server side **as it is wired up from GTM** — mapping the dataLayer event into a CAPI payload, sharing `event_id` with the Pixel, and the sGTM tag. For the Conversions API in its own right — the full field matrix, per-field normalization with Meta's published hash vectors, token setup, error handling, and payload validation — use the **`meta-conversions-api`** skill, which is distilled directly from Meta's official documentation. Where the two disagree, that one wins: this file's source is a research synthesis, and syntheses drift.

## Contents

- [Server event fields](#server-event-fields)
- [user_data: the identity block](#user_data-the-identity-block)
- [Normalization before hashing](#normalization-before-hashing)
- [custom_data](#custom_data)
- [fbp and fbc](#fbp-and-fbc)
- [Deduplication](#deduplication)
- [Event Match Quality](#event-match-quality)
- [A complete implementation](#a-complete-implementation)
- [Limited Data Use](#limited-data-use)
- [Restricted categories](#restricted-categories)

## Server event fields

`POST https://graph.facebook.com/v{API_VERSION}/{dataset_id}/events?access_token={token}`

Use a **System User token** and keep it server-side. A direct integration needs **no App Review and no permissions** — Meta's docs say so explicitly: *"There is no need to go through App Review or request any permissions."* The `ads_management` / `events_management` + App Review path applies only to platforms sending on behalf of clients. See the **`meta-conversions-api`** skill for token setup.

Two notes before you copy the version out of any example, including the ones below:

- **Pin a current Graph API version deliberately.** Examples in this file use `v21.0` as a placeholder; Graph API versions age out on a published schedule and Meta ships new ones regularly. Check the [Graph API changelog](https://developers.facebook.com/docs/graph-api/changelog) and pin a supported version — an unsupported one degrades to default behavior rather than erroring cleanly.
- **`{dataset_id}` is the Pixel ID.** Meta renamed Pixels to Datasets in Events Manager; the numeric value is the same one you pass to `fbq('init')`. The docs use both names for one identifier, which reads like two config values. Name the env var once (`META_DATASET_ID`) and don't keep both.

| Field | Required? | Notes |
|---|---|---|
| `event_name` | **Required** | Standard or custom name; used with `event_id` for dedup |
| `event_time` | **Required** | Unix **seconds**, GMT. Up to **7 days** in the past — one stale event **errors the entire request**, not just that event |
| `user_data` | **Required** | Hashed contact info + non-hashed technical IDs |
| `action_source` | **Required** | `website`, `app`, `phone_call`, `chat`, `email`, `physical_store`, `system_generated`, `business_messaging`, `other`. All enable measurement + custom audiences; all except `physical_store` enable optimization |
| `event_source_url` | Required for website events | Must begin with `http(s)://` |
| `event_id` | Optional but effectively required | The dedup key. Any unique string |
| `custom_data` | Optional | Business/commerce data |
| `opt_out` | Optional | `true` = attribution only, not optimization |
| `data_processing_options` | Optional | `["LDU"]` to enable Limited Data Use; `[]` to explicitly opt out |
| `data_processing_options_country` | If LDU | `1` = USA; `0` = ask Meta to geolocate |
| `data_processing_options_state` | If LDU | `1000` = California; `0` = ask Meta to geolocate |
| `app_data` / `extinfo` | Required for app events | Device/OS info (16 indexed values) |
| `referrer_url` | Optional | Prior page |

Add `test_event_code` (top level, sibling of `data`) while validating in Events Manager → Test Events. **Remove it in production** — events carrying a test code don't count toward optimization, which is a silent way to ship a pixel that measures nothing.

The `event_time` 7-day rule deserves care in a queue: if a job retries for days, or you backfill, a single old event rejects the whole batch. Guard it explicitly rather than trusting your queue's timing.

## user_data: the identity block

**SHA-256 hashed** (normalize first — see below):

| Param | Field |
|---|---|
| `em` | Email |
| `ph` | Phone |
| `fn` / `ln` | First / last name |
| `ge` | Gender (`f` / `m`) |
| `db` | Date of birth (`YYYYMMDD`) |
| `ct` | City |
| `st` | State (2-letter code) |
| `zp` | Zip / postal |
| `country` | Country (ISO 3166-1 alpha-2) |
| `external_id` | Your CRM/user ID — hashing recommended, not strictly required |

**Never hashed** — these are technical identifiers, and hashing them destroys them silently:

`client_ip_address`, `client_user_agent`, `fbc`, `fbp`, `subscription_id`, `fb_login_id`, `lead_id`, `page_id`, `page_scoped_user_id`, `ctwa_clid` (click-to-WhatsApp), `ig_account_id`, `ig_sid`; app-only: `anon_id`, `madid`.

Hashed fields are conventionally sent as **arrays** (`em: ["<hash>"]`), which also lets you send multiple values for one user.

**Do not mix hashed and unhashed values in the same field.** On the browser Pixel, `fbq('init', ID, {em, ph})` takes **plaintext** — the library normalizes and hashes for you. On the server you pre-hash everything. Those are different contracts for the same field name, which is exactly why implementations get it backwards.

**Automatic Advanced Matching (AAM)** scrapes form fields in the browser automatically; **Manual Advanced Matching** sends explicit values. On collision, AAM wins.

## Normalization before hashing

An un-normalized hash is not a weaker match — it's a **wrong** match. `" Ann@X.com "` and `"ann@x.com"` produce entirely unrelated digests, so the identity simply fails to resolve and EMQ drops with no diagnostic pointing at the cause.

| Field | Normalize to |
|---|---|
| `em` | trim, lowercase |
| `ph` | digits only **including country code**, no `+`, no spaces or separators |
| `fn` / `ln` | lowercase, trim |
| `ge` | `f` or `m` |
| `db` | `YYYYMMDD` |
| `ct` | lowercase, remove spaces and punctuation |
| `st` | 2-letter code, lowercase |
| `zp` | lowercase; 5-digit for US (drop the `+4`) |
| `country` | ISO 3166-1 alpha-2, lowercase |

Phone is where this goes wrong most: a national-format number (`0155 512 34`) hashed without expanding to the country code matches nobody.

## custom_data

`value` (float), `currency` (ISO 4217 — **required for Purchase**), `content_name`, `content_category`, `content_ids` (array), `contents` (array of `{id, quantity, item_price, delivery_category}`), `content_type` (`product` / `product_group`), `order_id`, `predicted_ltv` (float), `num_items` (**InitiateCheckout only**), `search_string` (**Search only**), `status` (**CompleteRegistration only**), `delivery_category` (`in_store` / `curbside` / `home_delivery`), plus arbitrary custom properties.

Meta strictly requires only **`currency` + `value` on Purchase**. For Advantage+ catalog (dynamic) ads, `contents` / `content_ids` + `content_type` are required on `ViewContent`, `AddToCart`, `Search`, and `Purchase`.

The event-scoped parameters are worth respecting: `num_items` on a `Purchase` isn't validated away, it's just noise in a field Meta reads for a different event.

## fbp and fbc

Two first-party cookies, and the single biggest lever on match quality.

- **`_fbp`** — browser ID, ~90-day lifetime: `fb.<subdomain_index>.<creation_timestamp_ms>.<random_number>`, e.g. `fb.1.1596403881668.1116446470`. `subdomain_index`: `0`=`com`, `1`=apex (`example.com`), `2`=`www.example.com`. On the server with no cookie present, use `1`.
- **`_fbc`** — click ID, set **only** when `fbclid` is present: `fb.<subdomain_index>.<creation_timestamp_ms>.<fbclid>`. Built from the `fbclid` URL query parameter when a user arrives from a Meta ad.

Rules:

- **Do not fabricate `fbc` if there was no ad click.** It's an attribution claim, not a tracking cookie.
- **`fbclid` is case-sensitive — do not lowercase or transform it.** It flows through the same code paths as email, and a well-meaning `.toLowerCase()` destroys it.
- `fbp` is the identity anchor (Meta uses it in place of `external_id` when the latter is absent); `fbc` is the attribution signal. Send **both** when available.
- **iOS 17 Link Tracking Protection strips `fbclid` from URLs** (killing `fbc`); **iOS 26 Advanced Fingerprinting Protection** extends this. Persist `fbc`/`fbp` server-side on the first hit rather than reading them at conversion time.

Your webhook has no browser context, so capture them at checkout and persist them on the order:

```js
const getCookie = n => document.cookie.match('(^|;)\\s*' + n + '\\s*=\\s*([^;]+)')?.pop();

let fbc = getCookie('_fbc');
if (!fbc) {                                     // landed with ?fbclid= before the cookie was set
  const fbclid = new URLSearchParams(location.search).get('fbclid');
  if (fbclid) fbc = `fb.1.${Date.now()}.${fbclid}`;   // fbclid verbatim — no case change
}

await api.attachAttribution({ cartToken, fbp: getCookie('_fbp'), fbc });
```

Take `client_ip_address` from the request that hit **your** server (first hop of `X-Forwarded-For`), never from a value the browser supplied.

## Deduplication

Meta collapses a browser event and a server event when **`event_name` AND `event_id` both match**, within a **48-hour** window. After 48 hours they are treated as separate events. If a server and browser event arrive within ~5 minutes of each other, Meta favors the browser/app event.

Offline events dedup on a **7-day** window, by `order_id` or user.

The rule, restated because it's the whole ballgame: **derive, don't generate.** Two `uuidv4()` calls in two runtimes produce two IDs and two conversions. See SKILL.md → the dedup contract for how to hand an ID across the boundary when there's no natural shared key.

In Events Manager a working setup shows **"1 event from 2 sources."** Two rows means no dedup. This is the only place the failure is visible.

## Event Match Quality

A score **0–10** reflecting how well server events match Meta accounts. Refreshes on a rolling ~48-hour window; currently web events only. Meta recommends **6+** as healthy for optimization.

Highest-impact parameters: **hashed email (`em`)** and **hashed phone (`ph`)**, plus **`fbc`**, **`fbp`**, and **`external_id`**. Supporting: `fn`/`ln`/`ct`/`st`/`zp`/`db`/`ge`/`country`. Purchase events commonly score highest simply because they carry the most identity data.

EMQ is a **diagnostic, not a ROAS metric** — chasing the number by stuffing in weakly-normalized fields makes it worse, not better.

> Meta does **not** publish per-parameter point contributions. Figures like "+4 for email, +3 for phone" circulate in practitioner blogs and are **unofficial estimates** — don't design against them.

If EMQ is low on Purchase, the near-certain cause is that `fbc`/`fbp` aren't reaching the server. Check that first, before adding more identity fields.

## A complete implementation

```js
const crypto = require('node:crypto');

const API_VERSION = 'v21.0';   // pin deliberately; check Meta's changelog for a current version

const sha256 = v => crypto.createHash('sha256').update(String(v), 'utf8').digest('hex');
const arr = v => (v === undefined ? undefined : [v]);

const norm = {
  email: v => v.trim().toLowerCase(),
  phone: v => String(v).replace(/\D/g, ''),          // country code included, no '+'
  name:  v => v.trim().toLowerCase(),
  city:  v => v.trim().toLowerCase().replace(/[\s.,'-]/g, ''),
  zip:   v => v.trim().toLowerCase().split('-')[0],
  cc:    v => v.trim().toLowerCase()
};

const clean = o => Object.fromEntries(
  Object.entries(o).filter(([, v]) =>
    v !== undefined && v !== null && !(Array.isArray(v) && v.length === 0))
);

async function sendPurchase(order, ctx, consent) {
  // CAPI bypasses the browser, so it bypasses the browser's consent gate.
  // The webhook fires later, with no browser to ask. Check the persisted state.
  if (consent?.ad_user_data !== 'granted') return { skipped: 'no_consent' };

  const eventTime = Math.floor(new Date(order.createdAt).getTime() / 1000);
  // One event older than 7 days rejects the ENTIRE request.
  if (eventTime < Math.floor(Date.now() / 1000) - 7 * 86400) {
    return { skipped: 'outside_7d_window' };
  }

  const a = order.billingAddress || {};

  const event = {
    event_name: 'Purchase',
    event_time: eventTime,
    event_id: `purchase.${order.id}`,        // MUST equal the Pixel's eventID
    event_source_url: ctx.sourceUrl,
    action_source: 'website',
    user_data: clean({
      em:          arr(sha256(norm.email(order.email))),
      ph:          a.phone   ? arr(sha256(norm.phone(a.phone)))     : undefined,
      fn:          a.firstName ? arr(sha256(norm.name(a.firstName))) : undefined,
      ln:          a.lastName  ? arr(sha256(norm.name(a.lastName)))  : undefined,
      ct:          a.city    ? arr(sha256(norm.city(a.city)))       : undefined,
      st:          a.provinceCode ? arr(sha256(norm.cc(a.provinceCode))) : undefined,
      zp:          a.zip     ? arr(sha256(norm.zip(a.zip)))         : undefined,
      country:     a.countryCode ? arr(sha256(norm.cc(a.countryCode))) : undefined,
      external_id: arr(sha256(String(order.customerId))),
      // raw — hashing any of these silently destroys them
      client_ip_address: ctx.ip,
      client_user_agent: ctx.userAgent,
      fbc: ctx.fbc,
      fbp: ctx.fbp
    }),
    custom_data: clean({
      currency: order.currency,                              // ISO 4217 code
      value: Number(order.totalPrice.toFixed(2)),            // number
      content_type: 'product',
      content_ids: order.lineItems.map(l => String(l.sku)),  // String() — catalog match
      contents: order.lineItems.map(l => ({
        id: String(l.sku),
        quantity: l.quantity,
        item_price: Number(l.unitPrice.toFixed(2))
      })),
      order_id: String(order.orderNumber)
    })
  };

  const res = await fetch(
    `https://graph.facebook.com/${API_VERSION}/${process.env.META_DATASET_ID}/events`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: [event], access_token: process.env.META_CAPI_TOKEN })
    }
  );

  const body = await res.json();
  if (!res.ok) {
    // 5xx/429 are retryable; 400 is a bad payload and will fail identically forever.
    throw Object.assign(new Error(`CAPI ${res.status}: ${JSON.stringify(body)}`), {
      retryable: res.status >= 500 || res.status === 429
    });
  }
  return body;   // { events_received, messages, fbtrace_id }
}
```

Fire this from the **payment webhook**, not the thank-you page — that's the whole point of the redundancy. Enqueue rather than calling inline so a Meta outage doesn't make your payment provider retry the webhook.

## Limited Data Use

The flag for **US state privacy laws** (CCPA/CPRA and successors) — **not** a GDPR mechanism. It does nothing for EU traffic.

- `data_processing_options: ["LDU"]` enables it. An **empty array** explicitly specifies the event should *not* be processed under LDU restrictions.
- If you set a country you **must** also set a state, otherwise Meta geolocates the whole event.
- `data_processing_options_country: 1` = USA, `data_processing_options_state: 1000` = California; `0` for either asks Meta to geolocate.

## Restricted categories

Meta's Business Tools Terms **require** SHA-256 hashing of contact information and **prohibit** sending data that:

- is from or about **children under 13**;
- includes **identifiers Meta doesn't permit** (Social Security numbers, credit card numbers);
- includes or is based on **health, financial, consumer-report, or other sensitive-category information**.

Meta's **signals filtering** auto-detects and blocks potentially sensitive health-related data. Since **November 2024 / early 2025**, Meta categorizes data sources and applies three restriction tiers to health/wellness (and financial) sources:

1. **Core setup** — custom events must be registered in Events Manager or they're dropped; URL/UTM and custom params stripped
2. **Restrictions on certain standard events** — e.g. blocking `Lead` / `AddToCart` / `Purchase`
3. **Full restrictions** — only upper-funnel Awareness/Engagement/Traffic objectives remain

Meta retains Event Data up to two years.

If your site touches health, financial, or other sensitive categories, expect auto-restriction, do not send event-level identity or content, and get counsel involved. See `references/consent-and-privacy.md`.
