# Troubleshooting & Migration

## Contents
- [Diagnosing a pixel that isn't working](#diagnosing-a-pixel-that-isnt-working)
- [Pixel Helper](#pixel-helper)
- [FAQs](#faqs)
- [Migrating from deprecated pixels](#migrating-from-deprecated-pixels)

## Diagnosing a pixel that isn't working

Work outward from the page, in this order — each step rules out a whole class of cause, and skipping to the interesting hypothesis first is how these turn into hour-long dead ends.

**1. Does the pixel load at all?**
Open the page with the Pixel Helper. No badge on the icon means no pixel was found: the base code isn't on this page, is outside `<head>`, is blocked by an ad blocker, or is blocked by CSP. Check the browser console for CSP violations against `connect.facebook.net`, and the network tab for `fbevents.js`.

**2. Does it load but not fire the event?**
Confirm the event call actually executes — put a `console.log` next to it, or check that the click handler is bound at all. A `fbq('track', ...)` inside a component that never mounts, or bound before the element exists in the DOM, fires never and errors never.

**3. Does it fire but with bad data?**
This is the common one, and the most expensive, because everything *looks* fine. Check the payload against the rules in `standard-events.md`: `value` a number, `currency` an ISO code, `contents` entries carrying both `id` and `quantity`, `content_type` being `'product'`. Run `scripts/check_pixel.py` over the source to catch these mechanically.

**4. Does it fire correctly but not appear in Events Manager?**
Wait a few minutes and refresh — ingestion is not instant. For Commerce Manager's Events Data Sources tab specifically, recognition can take up to **24 hours**.

**5. Is it firing too much?**
On a page with more than one pixel ID, plain `track` fires on *all* initialized pixels. See `advanced.md` → Multiple pixels. This shows up as one agency's pixel mysteriously receiving another's events.

## Pixel Helper

A Chrome extension that inspects the page for pixel code. The badge shows how many events fired; no badge means no pixel is installed. Requires Chrome and a logged-in Facebook account.

One expected false alarm worth pre-empting with the user: on pages where events are bound to **button clicks**, the Helper reports an error before the click, because it expects on-load firing. Clicking the button dismisses it. That is not a bug in the implementation.

## FAQs

**A URL 404s when the Click ID is added.** URL shorteners and vanity URLs sometimes rewrite `&fbclid={id}` to `?fbclid={id}` (or vice versa), breaking the URL. It's a redirect-handling problem on the site's side.

**Query string parameters like the Click ID go missing.** The page either doesn't accept URL parameters at all, or rejects unexpected appended ones. Fix on the website side — either accept the parameters or ignore `fbclid` cleanly so the redirect still works.

**Does the pixel hurt site performance?** It loads asynchronously and doesn't block rendering. Because every advertiser loads the same script, it's usually already in the browser cache.

## Migrating from deprecated pixels

The Conversion Tracking Pixel was deprecated in **February 2017** and no longer works. The old Custom Audience Pixel should also be migrated. Old code loads `fbds.js` and pushes to `_fbq` — if you see either, it needs replacing:

```js
// OLD — deprecated, does not work
_fbq.push(['addPixelId', '<PIXEL_ID>']);
_fbq.push(['track', 'Purchase', {'value': 0.00, 'currency': 'USD'}]);
_fbq.push(['track', 'CustomEvent', {'value': 0.00, 'currency': 'USD'}]);
```

Replace the snippet with the current base code (`assets/base-code.html`), then rewrite every event call:

```js
// NEW
fbq('track', 'Purchase', {value: 0.00, currency: 'USD'});
fbq('trackCustom', 'CustomEvent', {value: 0.00, currency: 'USD'});
```

The mapping is: `_fbq.push(['track', ...])` becomes `fbq('track', ...)` for the 17 standard events, and `fbq('trackCustom', ...)` for anything else. Image-tag equivalents move to `https://www.facebook.com/tr?id=FB_PIXEL_ID&ev=Purchase&cd[value]=0.00&cd[currency]=USD`.

Two things to check when migrating, both easy to miss in a mechanical find-and-replace: any event name that isn't one of the 17 standard events must move to `trackCustom`, not `track`; and the old image tags used `ev=<PIXEL_ID>` where the new ones use `id=<PIXEL_ID>&ev=<EventName>`.
