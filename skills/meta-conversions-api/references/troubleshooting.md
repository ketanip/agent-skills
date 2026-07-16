# Troubleshooting

## What the response actually tells you

*"The Conversions API returns minimal data to conserve network bandwidth. If the event payload is
valid, a `2xx HTTP` response code is returned. If invalid, a `4xx HTTP` response code is returned,
with minimal error details in the response body."*

Read that literally. `2xx` means **valid**, not **useful**. A success looks like:

```json
{"events_received": 1, "messages": [], "fbtrace_id": "A8s..."}
```

`events_received: 1` means one event was accepted for processing. It does not mean the event matched
a user, will be attributed, or will optimize anything. `messages: []` is not a health check.
Everything this API punishes — a hash of an un-normalized value, a hashed `fbp`, a fabricated `fbc`,
an `external_id` that's hashed here and raw in the browser — is *valid* and returns `2xx`.

**Therefore: never report a 200 as evidence the integration works.** The only positive signals are in
Events Manager (matched/attributed counts, EMQ, dedup rate) and the Test Events tool. If you can't
check those, the integration is unverified — say so.

## Error codes: what the docs do and don't say

The Conversions API troubleshooting page **does not publish a table of CAPI error codes.** It says
errors return `4xx` with *"minimal error details in the response body"* and directs you to the shared
Facebook API infrastructure, since *"under the hood, all Facebook APIs share the same
infrastructure."*

The only error codes in the Conversions API documentation belong to the **Dataset Quality API**, for
dataset *creation* — not event ingestion:

| Error Code | Description |
|---|---|
| `2044055` | The `dataset_id` that was inputted doesn't exist. |
| `10` | The application doesn't have permission for this action. |

Any other numeric CAPI error code you may have seen quoted (the `100` / `190` / `2804xxx` family) is
**not in this documentation**. Don't hard-code handling for codes you haven't observed, and don't
present remembered values as documented. Log the full response body and `fbtrace_id`, branch on the
HTTP status, and read the actual error text.

Resources the page does point to:
[Developer Support](https://developers.facebook.com/support/),
[open bugs](https://developers.facebook.com/support/bugs/),
[Developer Community Forum](https://developers.facebook.com/community),
[Best Practices for Conversions API](https://www.facebook.com/business/help/308855623839366?id=818859032317965).

## Timeouts and retries

Specific, quotable numbers:

- **Set a request timeout of 1,500 ms.** *"To account for various network delays, we recommend
  setting a timeout of 1500 milliseconds on the request."*
- *"For the majority of requests, the response time will be under 600 milliseconds."*
- *"Network errors or malformed requests may cause events to be dropped. We recommend retrying the
  request in cases where the response indicates a non-client error, such as a timeout."*

So: retry timeouts and 5xx; do **not** retry 4xx — a malformed payload will be malformed again. A
5-second timeout is not a safer version of 1,500 ms; it's several seconds of a customer's checkout
spent waiting on an ad pipeline. Send asynchronously and don't let tracking failures fail a
conversion.

When you retry a deferred event, keep the original `event_time` (the transaction time) rather than
recomputing — and keep the same `event_id`, so the retry deduplicates instead of double-counting.

## Batching

- **Up to 1,000 events** in `data` per request. This is the only stated CAPI limit.
- **"If any event you send in a batch is invalid, we reject the entire batch."**
- Likewise for time: *"If any `event_time` in `data` is greater than 7 days in the past, we return an
  error for the entire request and process no events."*

Batching is therefore all-or-nothing. One event with a stale timestamp discards 999 good ones, and
the `4xx` gives you *minimal* detail about which. Validate before sending, keep batches small enough
to isolate failures, and if a batch is rejected, don't assume the first event is the culprit.

Meta's own recommendation is to *"send events as soon as they occur and ideally within an hour of the
event occurring"* — batching is a performance tool, not the default.

## Rate limits

*"There is no specific rate limit for the Conversions API."* Calls count as Marketing API calls,
which have their own rate-limiting logic and are **excluded from Graph API rate limits**. The only
stated limitation is the 1,000-events-per-call cap. See
[Marketing API Rate Limiting](https://developers.facebook.com/documentation/ads-commerce/marketing-api/overview/rate-limiting).

## Test Events

Events Manager → Data Sources → your Pixel → **Test Events** generates a test ID. Send it as
`test_event_code` at the **top level** of the request body (a sibling of `data`, not inside an event):

```json
{"data": [{"event_name": "ViewContent", "event_time": 1764975551,
           "event_id": "event.id.123", "event_source_url": "http://jaspers-market.com",
           "user_data": {"client_ip_address": "1.2.3.4", "client_user_agent": "test user agent"}}],
 "test_event_code": "TEST123"}
```

Two things people get wrong:

- **It is not a sandbox.** *"Events sent with `test_event_code` are not dropped. They flow into
  Events Manager and are used for targeting and ads measurement purposes."* Test traffic pollutes
  real data.
- **It must come out of production.** *"The `test_event_code` field should be used only for
  testing. You need to remove it when sending your production payload."* Gate it behind an env var
  that is unset in prod.

The [Payload Helper](https://developers.facebook.com/documentation/ads-commerce/conversions-api/payload-helper)
constructs and validates a payload for you, and its "Get Code" button emits Business SDK code in
several languages. Useful for confirming a shape before you write the client.

## The diagnostic ladder

When events "aren't working," the response body won't tell you which layer failed. Work down:

1. **Did it arrive?** Events Manager → Overview, within ~**20 minutes** of sending. Under *Connection
   Method* you can see which channel delivered it. If nothing arrives, it's transport: status code,
   token, pixel ID, endpoint.
2. **Was it received but not matched?** Overview shows events received *before* deduplication,
   discards from consent controls and other policies, and processing. Low matched-vs-raw → a
   `user_data` problem: check EMQ and normalization (`normalization.md`), not the request.
3. **Matched but double-counted?** → Event Deduplication tab. Low *Overlap* means the `event_id`
   isn't reaching both channels, or isn't unique.
4. **Matched but not attributed?** → `fbc` is the click-to-conversion link. Hashed, fabricated, or
   absent `fbc` is the usual cause.
5. **Arriving late?** → Event Freshness tab. Check whether `event_time` is the transaction time
   rather than the upload time.

## Firewalls

If your business has a firewall for outbound requests, see
[Crawler IPs and User Agents](https://developers.facebook.com/docs/sharing/webmasters/crawler#identify)
for Facebook's IP addresses — and note the docs' warning that *"the list of addresses changes
often."* Allow-listing by IP is a maintenance burden, not a one-time task.
