---
name: meta-pixel
description: Implement, debug, and verify Meta Pixel (Facebook Pixel) tracking on a website — base code install, standard/custom events, event parameters, advanced matching, consent gating, SPA tracking, catalog ads, and multi-pixel setups. Use this skill whenever the user mentions the Meta/Facebook Pixel, fbq, fbevents.js, pixel ID, conversion tracking, Events Manager, Pixel Helper, Advantage+ catalog ads, custom audiences, or asks to "track purchases/leads/signups for Facebook ads" — even if they never say the word "pixel". Also use when reviewing or fixing existing fbq() calls, since malformed parameters silently break ad optimization.
---

# Meta Pixel

The Meta Pixel is a JavaScript snippet that loads `fbevents.js` and exposes a single global function, `fbq()`. Every interaction with it is a call to that function. Events land in [Events Manager](https://business.facebook.com/events_manager), where they drive conversion reporting, ad optimization, and custom audiences.

The reason care matters here: a malformed event does not throw. `fbq()` accepts it, the page looks fine, and the data quietly fails to power optimization — a `value: '5.000,00'` string or a missing `quantity` key costs the advertiser money for weeks before anyone notices. Treat parameter shape as the load-bearing part of the job, not an afterthought.

## Start here: what is being asked?

| Situation | Go to |
|---|---|
| Pixel isn't installed yet | [Install the base code](#install-the-base-code) |
| Track a purchase/lead/signup/etc. | [Track an event](#track-an-event) |
| Framework routing, no full page reloads (React/Vue/Next/etc.) | `references/advanced.md` → SPA |
| Track a button click, scroll depth, or time on page | `references/advanced.md` |
| Two or more pixel IDs on one page | [Multiple pixels](#multiple-pixels-on-one-page) — the default `track` over-fires |
| Attach email/phone/name to events for better matching | `references/privacy-and-consent.md` → Advanced Matching |
| GDPR cookie banner, CCPA / Limited Data Use | `references/privacy-and-consent.md` |
| Advantage+ catalog ads, Collaborative Ads, Marketing API | `references/use-cases.md` |
| Events not showing up / Pixel Helper errors | `references/troubleshooting.md` |
| Full standard-event and parameter tables | `references/standard-events.md` |

## Install the base code

Put it between the `<head>` tags of **every page** you want to track — usually the site's persistent header/layout component. In `<head>` specifically, because it reduces the chance that a browser or third-party script blocks execution, and it fires before the visitor can leave.

Copy `assets/base-code.html` and replace the two occurrences of the pixel ID. The `fbq('track', 'PageView')` line at the bottom should stay — leave it intact.

Two things that are easy to get wrong:

- The pixel ID appears **twice** — once in `fbq('init', ...)` and once in the `<noscript>` image fallback. Replace both.
- Consent gating and Limited Data Use, if needed, must be configured *before* `fbq('init')` runs. Retrofitting them later is a rewrite of the snippet, so decide up front (see `references/privacy-and-consent.md`).

If the site has a Content Security Policy, allow scripts from `https://connect.facebook.net` (the pixel loads from both `/en_US/fbevents.js` and `/signals/config/{pixelID}`).

Then verify: load the page and confirm a `PageView` shows up in Events Manager, or use the [Pixel Helper](https://developers.facebook.com/documentation/meta-pixel/support/pixel-helper) Chrome extension. Don't call the install done without this — a pixel that loads but never fires looks identical to a working one from inside the code.

## Track an event

There are three kinds of conversion tracking. Reach for them in this order:

1. **Standard events** — 17 predefined actions (`Purchase`, `Lead`, `AddToCart`, `ViewContent`, …). Prefer these. Meta's optimization, catalog ads, and value-based bidding are built around them, so a standard event is worth more than an equivalent custom one.
2. **Custom events** — your own name, when nothing standard fits. Still usable for custom audiences. Names are strings, max 50 characters.
3. **Custom conversions** — URL-rule based, configured entirely in Events Manager with no code. Good when you can't touch the codebase.

```js
fbq('track', 'Purchase', {currency: 'USD', value: 30.00});   // standard
fbq('trackCustom', 'ShareDiscount', {promotion: 'share_10'}); // custom
```

Call it anywhere inside `<body>` — on page load for page-scoped events, or in a click/submit handler for interaction-scoped ones. Fire `Purchase` on the confirmation page (after the payment actually succeeded), not on the checkout button, unless you genuinely intend to count intent rather than revenue.

Pick the event that matches the user's actual funnel step; see the full table in `references/standard-events.md`. The common ones:

| Event | Fires when | Parameters that matter |
|---|---|---|
| `ViewContent` | Product/landing page viewed | `content_ids` or `contents`, `content_type`, `value`, `currency` |
| `AddToCart` | Added to cart | `contents`, `content_type`, `value`, `currency` |
| `InitiateCheckout` | Entered checkout | `contents`, `num_items`, `value`, `currency` |
| `Purchase` | Payment confirmed | **`currency` and `value` are required**, plus `contents` |
| `Lead` / `CompleteRegistration` | Signup or form submitted | `value`, `currency` (optional but enables value optimization) |
| `Search` | Search performed | `search_string`, `content_ids` |

### Parameter shape is where implementations break

The docs call these out as the recurring mistakes. Check every payload against them:

```js
// ✅ correct
fbq('track', 'Purchase', {
  value: 130,                                  // number, not a string
  currency: 'USD',                             // ISO 4217 code, not '$'
  content_type: 'product',                     // literally 'product' (or 'product_group')
  contents: [{id: 'SKU-1', quantity: 2}],      // array of objects; id AND quantity
});

// ❌ each of these silently degrades the event
value: '5000,00'                    // string with a comma
currency: '$'                       // symbol instead of code
content_ids: 'SKU-1,SKU-2'          // comma string instead of an array
contents: [{id: 'SKU-1'}]           // missing quantity
content_type: 'soap'                // must be 'product' / 'product_group'
```

For catalog ads, the IDs in `content_ids`/`contents` must match the product IDs in the catalog exactly — that join is what makes dynamic ads work at all.

Custom properties are allowed alongside the predefined ones (`compared_product: 'banner-shoes'`). Keys used for custom-audience definitions must not contain spaces.

If the site also sends server-side events via the Conversions API, pass a shared `eventID` as the fourth argument to `fbq('track')` so the browser and server events deduplicate.

## Multiple pixels on one page

This is the single most surprising behavior in the whole system, and worth internalizing before you touch a page with two pixel IDs.

`fbq('init', ...)` pushes the ID into a global queue, and every later `fbq('track', ...)` fires against **every initialized pixel** — regardless of which `init` call it appears after, and regardless of whether the pixels came from separate base-code blocks. Two agencies each dropping their own snippet will each receive the other's events, quietly skewing both sets of reports.

The fix is to name the target explicitly:

```js
fbq('init', 'PIXEL-A');
fbq('init', 'PIXEL-B');
fbq('track', 'PageView');                              // intentionally both

fbq('trackSingle', 'PIXEL-A', 'Purchase', {value: 4, currency: 'GBP'});
fbq('trackSingleCustom', 'PIXEL-B', 'Step4', {});
```

So: on any page with more than one pixel, use `trackSingle`/`trackSingleCustom` for everything except events you truly want on all of them. (Note `trackSingleCustom` does not validate custom data.)

## Verify before you call it done

Implementations that "look right" in the diff are exactly the ones that break, because nothing errors. Two checks:

1. Run `scripts/check_pixel.py <paths>` — it scans for `fbq()` calls and flags the malformed-parameter patterns above, missing base code, and `track` used on multi-pixel pages. It is a linter, not a substitute for step 2.
2. Load the page with the Pixel Helper extension and confirm the event fires with the parameters you expect. If the user can't do that, tell them plainly that the implementation is unverified and what they should look for in Events Manager.

## Reference files

- `references/standard-events.md` — all 17 standard events, their object properties, `custom_event_type` values for the Marketing API, and the full parameter table.
- `references/advanced.md` — SPAs, button clicks, scroll/visibility/page-percentage triggers, delayed fires, `<img>`-tag installs, automatic configuration, CSP.
- `references/privacy-and-consent.md` — advanced matching (the `em`/`ph`/`fn` user-data fields and their normalization rules), GDPR consent API, Limited Data Use for US states.
- `references/use-cases.md` — Advantage+ catalog ads, Collaborative Ads, Marketing API (`promoted_object`, value optimization, Aggregated Event Measurement), movies.
- `references/troubleshooting.md` — Pixel Helper, common errors, FAQs, migrating off the deprecated Custom Audience / Conversion Tracking pixels.
