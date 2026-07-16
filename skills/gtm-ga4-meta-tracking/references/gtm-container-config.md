# GTM Container Configuration

## Contents

- [Variable types](#variable-types)
- [Built-in variables](#built-in-variables)
- [Triggers](#triggers)
- [A worked container](#a-worked-container)
- [Custom HTML tags and consent](#custom-html-tags-and-consent)
- [Tag sequencing](#tag-sequencing)

## Variable types

| Variable type | What it captures |
|---|---|
| **Data Layer Variable** | Any key in the dataLayer; supports dot/bracket notation (`ecommerce.items.0.item_id`). "Version 2" reads full objects |
| **1st-Party Cookie** | Any readable cookie (`_ga`, `_fbp`, `_gcl_aw`) |
| **Custom JavaScript** | Return value of an anonymous function — can read anything the page's JS can |
| **JavaScript Variable** | A global `window.*` variable by name |
| **DOM Element** | Text or attribute of an element by ID or CSS selector |
| **Auto-Event Variable** | The element/attribute in a click/form auto-event (13 sub-types: Element, Element Type, Element ID, Classes, Target, URL, Text, …) |
| **URL** | Components of the current URL (full, host, path, port, query, fragment, protocol) |
| **Referrer** | The referring URL, full or component |
| **Constant / Lookup Table / RegEx Table** | Static values, or map input→output (Lookup = exact match; RegEx = pattern) |
| **User-Provided Data** | Aggregates email/phone/address from page/dataLayer/CSS selectors for Enhanced Conversions — **hashing handled by Google at send time** |
| **Consent State** | Current status of the Consent Mode signals |
| **Container/Environment metadata, Random Number, HTML ID, Debug Mode** | Utility values |

Two notes that matter more than they look:

- **DOM Element and CSS-selector-based variables are the fragile ones.** They break on any markup change, silently, and the tag keeps firing with an empty value. Prefer a dataLayer push from the application, which is a contract the app can be tested against.
- **The User-Provided Data variable takes plaintext.** This is the sanctioned Enhanced Conversions channel and it hashes for you. Feeding it a pre-hashed digest silently disables the feature.

## Built-in variables

~44 across 9 categories. Enable via Variables → Configure.

- **Page:** Page URL, Page Hostname, Page Path, Referrer
- **Utilities:** Event (the dataLayer `event` value: `gtm.js`, `gtm.dom`, `gtm.load`, or custom), Environment Name, Container ID, Container Version, Random Number, HTML ID, Debug Mode
- **Clicks:** Click Element, Click Classes, Click ID, Click Target, Click URL, Click Text
- **Forms:** Form Element, Form Classes, Form ID, Form Target, Form URL, Form Text
- **History:** New History Fragment, Old History Fragment, New History State, Old History State, History Source (SPA / `gtm.historyChange`)
- **Errors:** Error Message, Error URL, Error Line (`gtm.pageError`)
- **Scroll:** Scroll Depth Threshold (`gtm.scrollThreshold`), Scroll Depth Units (`gtm.scrollUnits`), Scroll Direction (`gtm.scrollDirection`)
- **Visibility:** Percent Visible (`gtm.visibleRatio`, 0–100), On-Screen Duration (`gtm.visibleTime`, ms)
- **Videos (YouTube):** Video Provider, Video Status, Video URL, Video Title, Video Duration, Video Current Time, Video Percent, Video Visible

Useful quirk: the built-in **Click variables are also populated by the Element Visibility trigger**, so you can identify which element became visible without a separate variable.

## Triggers

Triggers listen for events and, in firing, push data the variables then read.

| Trigger | dataLayer event |
|---|---|
| Page View / DOM Ready / Window Loaded | `gtm.js` / `gtm.dom` / `gtm.load` |
| Click – All Elements | `gtm.click` |
| Click – Just Links | `gtm.linkClick` |
| Form Submission | `gtm.formSubmit` |
| Scroll Depth | `gtm.scroll` (vertical/horizontal, % or px) |
| Element Visibility | `gtm.elementVisibility` |
| YouTube Video | `gtm.video` |
| History Change | `gtm.historyChange` (SPA route changes) |
| JavaScript Error | `gtm.pageError` |
| Timer | `gtm.timer` |
| **Custom Event** | matches any `event` value you push — the mechanism for ecommerce |
| Trigger Groups | fire only when multiple conditions are all met |

**Custom Event triggers are what your ecommerce schema runs on.** Name them after the event (`ce - purchase`) so the container reads like the dataLayer.

Don't put a "once per page" limit on `add_to_cart` — users add more than once, and the second add vanishes with no signal.

## A worked container

For the canonical purchase schema in `references/datalayer-schema.md`:

**Variables**

| Name | Type | Config |
|---|---|---|
| `dlv - ecommerce.items` | Data Layer Variable | `ecommerce.items`, v2 |
| `dlv - ecommerce.value` | Data Layer Variable | `ecommerce.value` |
| `dlv - ecommerce.currency` | Data Layer Variable | `ecommerce.currency` |
| `dlv - ecommerce.transaction_id` | Data Layer Variable | `ecommerce.transaction_id` |
| `dlv - event_id` | Data Layer Variable | `event_id` |
| `dlv - user_data` | Data Layer Variable | `user_data` |
| `const - GA4 Measurement ID` | Constant | `G-XXXXXXXXXX` |
| `const - Meta Pixel ID` | Constant | `1234567890` |
| `cookie - _fbp` | 1st-Party Cookie | `_fbp`, URI-decode off — **server-side only, see below** |
| `cookie - _fbc` | 1st-Party Cookie | `_fbc`, URI-decode off — **server-side only, see below** |
| `js - Meta content_ids` | Custom JavaScript | see `datalayer-schema.md` |
| `js - Meta contents` | Custom JavaScript | see `datalayer-schema.md` |
| `upd - User Provided Data` | User-Provided Data | from `user_data` (plaintext) |

**On the `_fbp` / `_fbc` cookie variables:** the browser Pixel does **not** need them — `fbevents.js` reads those cookies itself, and wiring them into an `fbq()` call achieves nothing. They exist for the **server**: sGTM's CAPI tag, or an attribution POST that persists them on the order so your webhook can send them later. If you're browser-only, skip both variables.

**Triggers:** Custom Event, one per dataLayer event — `ce - view_item`, `ce - add_to_cart`, `ce - purchase`.

**GA4 tags**

- `GA4 - Configuration` — Google Tag, Tag ID `{{const - GA4 Measurement ID}}`, trigger *Initialization – All Pages*. Set `send_page_view: false` if you push your own pageviews (SPA). Consent Settings: none needed — Consent Mode is built in.
- `GA4 - purchase` — GA4 Event tag, Event Name `purchase`, trigger `ce - purchase`. Tick **"Send Ecommerce data" → Data source: Data Layer**. That single checkbox picks up the whole `ecommerce` object; hand-mapping `items` is a common and unnecessary source of drift.

**Meta tags** — Custom HTML, with consent checks (below). `fbq()` shape belongs to the **`meta-pixel`** skill.

The GTM Community Gallery has Meta templates. They're fine, but check the version you pick actually exposes `eventID` — some don't, and without it you have no dedup, which is usually the reason you're building this at all.

## Custom HTML tags and consent

**Custom HTML tags are not consent-aware on their own.** A GA4 tag knows about Consent Mode; a Custom HTML tag containing `fbq()` knows nothing and fires whenever its trigger says so.

So on every Meta tag: **Consent Settings → Require additional consent for: `ad_storage`, `ad_user_data`, `ad_personalization`**.

This is the most common EU compliance bug in GTM containers, and it is invisible in every functional test — the tag fires, the event lands, everything works. It only shows up when someone opens the Network tab after clicking "Reject".

Don't tick "Fire tag even when consent is denied" to make a queued tag behave. That checkbox means what it says.

## Hosted checkouts where GTM cannot reach

Worth checking before you design the container, because it breaks the architecture at exactly the step that matters.

**Shopify's hosted checkout and thank-you page do not run your GTM container.** Since the checkout-extensibility migration, tracking there goes through a **Custom Pixel** in Shopify's Web Pixels API sandbox — a separate JS environment that **cannot see `window.dataLayer`** and cannot reach your container. The same shape of constraint applies to other hosted checkouts (some BigCommerce, Recharge, and PSP-hosted payment pages).

The consequence: on those platforms the browser `Purchase` comes from the sandbox (subscribing to the Web Pixels `checkout_completed` event), not from your container, and **your CAPI call from the payment webhook becomes the primary purchase signal** rather than the redundant one.

What still has to hold: **the `event_id` formula must be identical in both places.** The sandbox pixel and the webhook both derive `purchase.${order.id}` from the order — that's the only thing keeping dedup alive across two environments that can't talk to each other. This is the case where getting `event_id` right stops being hygiene and becomes the whole design.

Everything upstream of checkout (PDP, add-to-cart, cart) is normal storefront JS and works with the container as documented.

## Tag sequencing

The Meta base pixel must run before any event tag that calls `fbq()`. Use **Tag Sequencing** → "Fire a tag before" → the base tag, and tick **"Don't fire if setup tag fails"**.

Without it you get a race: on a fast conversion the event tag fires before `fbevents.js` has defined `fbq`, the call goes into a queue that never flushes, and the event is gone. It only affects fast clickers and cold caches, which is precisely why QA never reproduces it.
