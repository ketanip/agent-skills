# Server-Side GTM (sGTM)

## Contents

- [What sGTM actually is](#what-sgtm-actually-is)
- [Clients and the event data model](#clients-and-the-event-data-model)
- [FPID and FPLC](#fpid-and-fplc)
- [The dual-dispatch architecture](#the-dual-dispatch-architecture)
- [sGTM vs. your own backend](#sgtm-vs-your-own-backend)
- [Enrichment and transformations](#enrichment-and-transformations)
- [Hosting](#hosting)

## What sGTM actually is

A GTM container that runs on **your** infrastructure instead of the visitor's browser. The browser sends a request to your first-party domain; the container receives it, parses it into a common event data model, and dispatches to tags (GA4, Meta CAPI, Google Ads) from the server.

What it buys you, concretely:

- **First-party, server-set cookies** (`HttpOnly`, invisible to JS, resilient to Safari ITP's 7-day cap on JS-set cookies)
- **Control over what reaches each vendor** — you can strip parameters before dispatch instead of trusting a vendor tag not to collect them
- **Enrichment from server-side sources** your browser never had (CRM, Firestore, BigQuery)
- **Resilience** against ad blockers and script-blocking extensions, because the vendor endpoint isn't being contacted from the page

What it does **not** buy you: a consent workaround. Moving the call server-side changes the transport, not the lawful basis.

## Clients and the event data model

A **Client** claims incoming HTTP requests — the GA4 Client claims requests to the default GA4 collection paths — and unpacks them into `event_name` plus event data keys: `page_location`, `client_id`, `ip_override`, `user_agent`, ecommerce keys, and `x-ga-*` internal params. You read these with **Event Data** variables, which are the server-side analogue of Data Layer Variables.

The routing that makes this work is `transport_url` on the browser-side Google tag: set it to your sGTM domain and hits go to your server first instead of straight to Google.

## FPID and FPLC

The GA4 Client can run in **Server Managed** mode, setting the **FPID** cookie via a `Set-Cookie` header with the **HttpOnly** flag (default 2-year lifetime). FPID then generates the GA4 `client_id`.

The catch, and it's the one people hit: **HttpOnly cookies can't be read by JavaScript, which breaks cross-domain linking**, since the linker needs to read the ID and put it in a URL. Google's answer is **FPLC** — a non-HttpOnly hash of FPID with a ~20-hour lifetime, used for cross-domain. Both domains' server containers must belong to the same GTM account.

**Migrating from JavaScript Managed Client ID:** toggle it on. Otherwise every returning visitor gets a fresh FPID, and your new-user count inflates overnight while nothing appears broken.

Shopify's checkout runs on a different domain; the standard advice is to revert to JS-managed client ID there rather than fight the cross-domain case.

Consent gating can prevent FPID being set or read when `analytics_storage` is denied.

## The dual-dispatch architecture

The canonical GA4 + Meta CAPI setup:

1. Browser Google tag sends GA4 events to the **first-party `transport_url`** (your sGTM domain).
2. sGTM **GA4 Client** claims the request and builds the event data model.
3. That single event fans out: (a) the **GA4 tag** forwards to Google, and (b) the **Meta CAPI tag** fires.
4. The CAPI tag maps GA4 params → Meta params, hashes PII with SHA-256, attaches `fbp`/`fbc` (**unhashed**) plus `client_ip_address` / `client_user_agent`, and sends with the **same `event_id`** the browser Pixel used.
5. The browser Meta Pixel fires the same event with the same `event_id` → Meta dedups on `event_id` + `event_name` within 48h.
6. Consent is enforced at the tag level; sensitive params are stripped in sGTM before dispatch.

The `event_id` still has to originate in the page and ride along in the event data. sGTM doesn't solve provenance for you — a CAPI tag that generates its own ID is exactly as broken as a backend that does.

## sGTM vs. your own backend

Both are legitimate, and the trade-off is not about effort — it's about **what triggers the event**.

| | sGTM Meta CAPI tag | Your own backend/webhook |
|---|---|---|
| Triggered by | The browser reaching your sGTM endpoint | Your own server-side truth (payment webhook) |
| Survives ad blockers | Yes (first-party domain) | Yes |
| Survives the user closing the tab pre-fire | **No** — no browser hit, no event | **Yes** |
| Purchase truth | Whatever the page claimed | The payment processor confirmed it |
| Effort | Container config | Application code |

For `purchase` specifically, a webhook is the stronger source: the sGTM path still requires the browser to reach the thank-you page, so you keep the ad-blocker resilience but lose the bounce/close resilience. For upper-funnel events (`ViewContent`, `AddToCart`) there's no server-side truth to draw on and sGTM is the natural fit.

Many good setups do both: sGTM for the funnel, a webhook for purchase. If you do, they must agree on `event_id` — the webhook derives `purchase.${order.id}`, and so does the page.

## Enrichment and transformations

Things sGTM can do that the browser can't:

- **Enrich from server APIs** — Firestore, BigQuery, or an HTTP CRM lookup to attach LTV, plan tier, or a hashed identifier the page never had.
- **Reconstruct click IDs** — e.g. parse `gclid` out of the `_gcl_aw` cookie for Shopify checkout sandboxes where auto-tagging doesn't survive.
- **Strip or anonymize before forwarding** — remove PII from `page_location`, drop UTM tokens, redact sensitive params. This is the mechanism for GA4's PII policy: enforce it at the server rather than hoping every page's URLs stay clean.
- **Cookie/pixel mechanics** — `/set_cookie` and `sendPixelFromBrowser` / `send_pixel` instructions (chunked responses) handle both first- and third-party cookie needs.

**Transformations** apply across multiple tags at once, which makes them the right place for "never send X to anyone" rules — a per-tag override is one forgotten checkbox away from leaking.

## Hosting

- **Google Cloud Run** — pay-per-use, self-managed. You own scaling, logging, and the domain mapping.
- **Managed hosts (e.g. Stape)** — add EU hosting for GDPR, an Anonymizer to strip GA4 params, Cookie reStore via Firestore, SSO.

If you serve EEA users and want to reduce transfer exposure, EU-region hosting is the practical lever — see `references/consent-and-privacy.md`.

Cost note: sGTM is a always-on server. A low-traffic site pays for idle capacity it didn't need; the architecture earns its keep on volume, on ITP-heavy audiences, or where the parameter-stripping control is itself the requirement.
