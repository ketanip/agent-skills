# Product-Specific Requirements

Each Meta ad product consumes pixel events differently and imposes its own required-parameter contract. Getting the base events firing is not enough — if the product's required properties are missing, the ads simply don't work, usually with no error anywhere.

## Contents
- [Advantage+ catalog ads](#advantage-catalog-ads)
- [Collaborative Ads](#collaborative-ads)
- [Marketing API](#marketing-api)
- [Movies](#movies)
- [Custom audiences](#custom-audiences)

## Advantage+ catalog ads

Dynamically builds ads from a product feed, so the pixel's product IDs are the join key to the catalog.

Required events, each with **either `content_ids` or `contents`**:

| Event | Required object properties |
|---|---|
| `ViewContent` | `content_ids` or `contents` |
| `AddToCart` | `content_ids` or `contents` |
| `Purchase` | `content_ids` or `contents` |

**The IDs must match the IDs in the product catalog exactly.** This is the whole mechanism — a mismatched SKU means the ad can't find the product and the campaign underdelivers.

```js
fbq('track', 'AddToCart', {
  value: .5,
  currency: 'USD',
  content_ids: ['201', '301']       // or use contents, below
});

fbq('track', 'AddToCart', {
  value: .5,
  currency: 'USD',
  contents: [
    {id: '301', quantity: 1},
    {id: '401', quantity: 2}
  ]
});
```

Prerequisites: a Facebook Page for the business, the base code installed, Ads Manager access. Afterward, use Commerce Manager to set up the catalog and confirm it recognizes the pixel as an events data source — that recognition can take up to **24 hours**, so don't treat a same-day absence as a bug.

## Collaborative Ads

Lets a producer (e.g. a CPG brand) run campaigns driving to a seller's site. The **seller** implements the pixel. Access is limited — the user needs a Meta representative.

Stricter than the general spec:

| Event | Required | Optional |
|---|---|---|
| `ViewContent` | `contents` or `content_ids`, and `content_type` | `currency`, `value` |
| `AddToCart` | `contents`, `content_type`, `currency`, `value` | — |
| `Purchase` | `contents`, `content_type`, `currency`, `value` | — |

Constraints specific to Collaborative Ads:
- `content_type` must be `"product"`. `"product_group"` and everything else is unsupported.
- Product Group IDs are not supported in `contents`.
- The minimal `content_ids`-only form is valid for `ViewContent` **only** — never for `AddToCart` or `Purchase`.
- `value` means different things per event: item value for `ViewContent`; value of the items just added for `AddToCart` (not the basket total); full basket total including shipping and tax for `Purchase`.

```js
fbq('track', 'Purchase', {
  contents: [
    {id: 'SKU-1', quantity: 2},
    {id: 'SKU-2', quantity: 1},
  ],
  content_type: 'product',
  value: 130,
  currency: 'USD',
});
```

The documented common mistakes, all of which pass silently:

- `contents: [{id: 'SKU-123'}]` — missing `quantity`.
- `content_ids: 'SKU-123,SKU-456'` — a comma string, not an array.
- `content_ids: []` — empty array.
- `content_type: 'soap'` — must be `'product'`.
- `value: '5000,00'` — string with a comma.
- `currency: '$'` — symbol instead of an ISO code.

## Marketing API

Pixel events feed audiences and conversion optimization from the API side.

**Optimize an ad set for a pixel event** via `promoted_object` on `/act_{AD_ACCOUNT_ID}/adsets`, using the event's `custom_event_type` (see `standard-events.md` for the full mapping):

```bash
curl -i -X POST "https://graph.facebook.com/v2.10/act_AD-ACCOUNT-ID/adsets
    ?name=Ad Set for Value Optimization
    &campaign_id=CAMPAIGN-ID
    &optimization_goal=VALUE
    &promoted_object={\"pixel_id\":\"PIXEL-ID\",\"custom_event_type\":\"PURCHASE\"}
    &billing_event=IMPRESSIONS
    &daily_budget=1000
    &attribution_spec=[{'event_type': 'CLICK_THROUGH', 'window_days':'1'}]
    &access_token=ACCESS-TOKEN"
```

`conversion_specs` is inferred from the objective and `promoted_object` — you cannot set it manually.

**Custom conversion insights** come back from Ads Insights as `offsite_conversion.custom.{id}` alongside standard ones like `offsite_conversion.fb_pixel_purchase`:

```bash
curl -i -G \
  -d 'fields=actions,action_values' \
  -d 'access_token=<ACCESS_TOKEN>' \
  https://graph.facebook.com/v2.7/<AD_ID>/insights
```

**Offsite conversions:** add the `fb_pixel` field to an ad's `tracking_spec`.

**Aggregated Event Measurement (iOS 14.5+):** measurement for iOS 14.5 users, using statistical modeling to fill gaps. It caps each domain at **8 configured, prioritized conversion events** — so when a user wants to track a dozen events, this is the constraint that decides which ones matter. Requires domain verification.

## Movies

A niche vertical with its own parameter shape. `content_ids` is a **single pipe-delimited string**, not the usual array:

```js
fbq('track', 'ViewContent', {
  content_ids: ['partner_movie_id|partner_theater_id|showtime'],  // in that order; showtime is ISO 8601
  movieref: 'fb_movies'   // or '' if the referrer lacks eventref=movieref
});
```

Where each event goes: `ViewContent` on the campaign landing page, `InitiateCheckout` on the payment page (with `num_items` = ticket count), `Purchase` on the payment confirmation page (with `currency`, `num_items`, `value` = total), and `PageView` on every *other* page of the checkout flow.

`movieref` is `'fb_movies'` when the referrer URL contains `eventref=movieref` as a query parameter, and an empty string otherwise.

## Custom audiences

Once events or custom conversions are tracked, visitors can be segmented into audiences in Events Manager — no additional code. Requirements are only that the base code is installed, events are firing, and the user has Ads Manager access.

The code-side constraint worth remembering: **parameter keys used to define an audience must not contain spaces.** Verify events appear correctly in Events Manager first — an audience can't be built on an event Meta isn't receiving.
