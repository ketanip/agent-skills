# Deduplication and Event Match Quality

Two separate concerns that both determine whether your events are worth anything:
**deduplication** decides whether a conversion is counted once or twice; **Event Match Quality**
decides whether it is attached to a person at all.

## Deduplication

Meta recommends running CAPI *alongside* the Pixel — a "redundant setup" — because events lost on the
browser side (network failures, blockers) still arrive via the server. The cost of that redundancy is
that you must deduplicate, or every conversion counts twice.

> Advertisers who don't send the same event twice via both channels don't need deduplication at all.

### Method 1: `event_id` + `event_name` (recommended)

An event is deduplicated when **both** match between channels:

1. The Pixel's `eventID` matches CAPI's `event_id`.
2. The Pixel's `event` matches CAPI's `event_name`.

```js
fbq('track', 'Purchase', {value: 12, currency: 'USD'}, {eventID: 'order-10432'});
fbq('trackSingle', 'PIXEL_ID', 'Purchase', {value: 12, currency: 'USD'}, {eventID: 'order-10432'});
fbq('track', 'Lead', {}, {eventID: 'EVENT_ID'});   // no value/currency? still works
```
```html
<img src="https://www.facebook.com/tr?id=PIXEL_ID&ev=Purchase&eid=EVENT_ID"/>
```
```json
{"event_name": "Purchase", "event_id": "order-10432"}
```

Note the `eventID` is the **fourth** argument to `fbq('track', ...)`, inside the optional `eventData`
object. (Browser-side specifics belong to the `meta-pixel` skill.)

**Choosing the value.** An order number or transaction ID is ideal — intrinsically unique per
conversion and stable across retries. Meta's own framing: two purchases with order numbers 123 and
456 must send their respective numbers, so the four total events (two browser, two server) resolve to
two conversions rather than four. For events with no intrinsic ID, a random value works *so long as
the same random number reaches both channels* — which means generating it once and threading it
through, not calling `uuid()` independently on each side.

**The windows that bite:**

- Dedup applies only **within 48 hours** of the first event with a given `event_id`. Same key
  combination to the same Pixel ID inside 48 hours → subsequent events discarded.
- The docs also state that for a matching `event_name`, if a match is found between events sent
  within 48 hours of each other, only the first is considered.
- If server and browser events arrive within ~**5 minutes** of each other, **the browser/app event is
  favored**.
- Otherwise, if the events don't differ meaningfully in content, Meta *"generally prefer[s] the event
  that is received first."*

### Method 2: `fbp` and/or `external_id`

Send `event_name` plus `fbp` and/or `external_id` consistently across both channels; Meta compares
the combination and removes duplicates.

Its limitations are real and asymmetric:

- It generally only works **browser first, then server**. *"Server events will not be discarded if a
  browser event has not been received in the past 48 hours, even if an identical browser event
  arrives after the server event."*
- It **does not deduplicate within a single source.** Two identical browser events, or two identical
  server events, are both kept.

Prefer method 1. Reach for method 2 when you genuinely cannot thread a shared ID through both sides.

### Verifying dedup

Events Manager → Overview → *Event Details* for an event type → **Event Deduplication** tab:

- **Rate of Events Deduplicated** — percentage deduplicated per source. Higher is better; a warning
  appears when it's too low. More dedup parameters can improve it.
- **Rate of Deduplication Key Usage** — percentage of events from each source containing each dedupe
  key. **Overlap** is the percentage carrying a given key received from *both* sources (as a
  percentage of the source with fewer events). **Low overlap means you are sending non-unique keys
  from one/either source, or sending the key from only one source** — which is exactly what a
  mismatched `event_id` looks like from the outside.

## Event Match Quality

EMQ is a **score out of 10** indicating how effective the customer information sent from your server
may be at matching event instances to a Meta account. Calculated from which `user_data` parameters
arrive, the quality of that information, and the percentage of event instances actually matched.
**Calculated in real time.**

Meta's guidance: *"Where possible, we typically recommend that you aim for an Event Match Quality
score of 6.0 or higher,"* and a high score *"can help decrease your cost per action."*

**EMQ is web-only.** For offline, physical store, app events, conversion leads, or anything in
alpha/beta, the docs say to contact your Meta representative instead.

Two ways to read it: Events Manager → Overview for the Pixel (click the score for details and
recommendations), or the Dataset Quality API.

### Dataset Quality API

```
GET /v25.0/dataset_quality
    ?dataset_id=<DATASET_ID>
    &agent_name=<AGENT_NAME>
    &access_token=<ACCESS_TOKEN>
    &fields=web{event_match_quality,event_name}
```

```json
{
  "web": [
    {
      "event_match_quality": {
        "composite_score": 6.2,
        "match_key_feedback": [
          {"identifier": "user_agent",   "coverage": {"percentage": 100}},
          {"identifier": "external_id",  "coverage": {"percentage": 100}}
        ]
      },
      "event_name": "pLTVPurchase"
    }
  ]
}
```

`composite_score` is the EMQ; `match_key_feedback` reports per-identifier **coverage** — the share of
events carrying that key. Coverage is the actionable half: a key at 0% is one you're not sending, and
a key present on every event that still isn't lifting the score is a normalization problem, not a
coverage problem.

Intended use: monitor EMQ per event alongside match keys, build a trendline, and alert on drops in
score or key coverage. A silent normalization regression shows up here and essentially nowhere else.

The API also exposes **event coverage**, **event deduplication**, **data freshness**, and
**Additional Conversions Reported (ACR)** — ACR estimates how many conversions are measured as a
result of your CAPI setup. Ownership/access requirements and the full field list:
[Dataset Quality API](https://developers.facebook.com/documentation/ads-commerce/conversions-api/dataset-quality-api).
All EMQ diagnostic fields:
[ads-pixel-capiemq reference](https://developers.facebook.com/docs/marketing-api/reference/ads-pixel-capiemq).

### Raising EMQ

In rough order of leverage:

1. **Fix normalization before adding fields.** A wrongly-normalized `em` scores like a missing one.
   Verify against the vectors in `normalization.md` first — otherwise you're adding keys to a broken
   pipeline.
2. **Send `client_ip_address` + `client_user_agent` on every event.** Free, unhashed, and the docs
   call them out as improving matching and delivery. They must come from the customer's request
   (see `normalization.md`).
3. **Send `fbc` and `fbp` whenever available**, unhashed and correctly formatted. Never fabricate
   `fbc`.
4. **Add `external_id`**, consistently across every channel — it lets a match made once on any
   channel carry to later events.
5. **Add the address block** (`ct`, `st`, `zp`, `country`) — weak alone, useful combined. You already
   have it at checkout.
6. **Mirror the browser's parameters server-side**: *"make sure to apply the same set of customer
   information parameters your system is currently sharing to the browser side to the server side."*

### Event freshness

Distinct from EMQ, and also monitored: Events Manager → Overview → *Event Details* → **Event
Freshness** shows average delay from Real Time to Weekly. Meta recommends minimizing the gap between
`event_time` and when the event is shared — *"as close to real-time as possible"* — and sending
events ideally **within an hour** of occurring. Batching once a day is legal (7-day window) and still
costs you.
