# Standard Events & Parameters Reference

## Contents
- [The 17 standard events](#the-17-standard-events)
- [Object properties](#object-properties)
- [Choosing between content_ids and contents](#choosing-between-content_ids-and-contents)
- [Custom events](#custom-events)
- [Custom conversions](#custom-conversions)

## The 17 standard events

Fired with `fbq('track', '<EventName>', {...})`. The event name is case-sensitive — `Purchase`, not `purchase`.

The `custom_event_type` column is the value used in the Marketing API's `promoted_object` when you want an ad set to optimize for that event.

| Event | Fires when | Object properties | `custom_event_type` |
|---|---|---|---|
| `AddPaymentInfo` | Payment info added in checkout (clicks "save billing information") | `content_ids`, `contents`, `currency`, `value` — all optional | `ADD_PAYMENT_INFO` |
| `AddToCart` | Product added to cart | `content_ids`, `content_type`, `contents`, `currency`, `value` — optional, but **`contents` required for Advantage+ catalog ads** | `ADD_TO_CART` |
| `AddToWishlist` | Product added to a wishlist | `content_ids`, `contents`, `currency`, `value` — optional | `ADD_TO_WISHLIST` |
| `CompleteRegistration` | Registration/subscription form completed | `currency`, `value`, `status` — optional | `COMPLETE_REGISTRATION` |
| `Contact` | Person contacts the business (phone, SMS, email, chat) | optional | `CONTACT` |
| `CustomizeProduct` | Person customizes a product (picks a t-shirt color) | optional | `CUSTOMIZE_PRODUCT` |
| `Donate` | Person donates funds | optional | — |
| `FindLocation` | Person searches for a store location intending to visit | optional | `FIND_LOCATION` |
| `InitiateCheckout` | Person enters the checkout flow | `content_ids`, `contents`, `currency`, `num_items`, `value` — optional | `INITIATE_CHECKOUT` |
| `Lead` | A sign-up is completed / person clicks pricing | `currency`, `value` — optional | `LEAD` |
| `Purchase` | Purchase made / checkout completed (lands on thank-you page) | `content_ids`, `content_type`, `contents`, `currency`, `num_items`, `value` — **`currency` and `value` are REQUIRED**; `contents` or `content_ids` required for Advantage+ catalog ads | `PURCHASE` |
| `Schedule` | Person books an appointment | optional | `SCHEDULE` |
| `Search` | A search is made | `content_ids`, `content_type`, `contents`, `currency`, `search_string`, `value` — optional; `contents`/`content_ids` required for catalog ads | `SEARCH` |
| `StartTrial` | Person starts a free trial | `currency`, `predicted_ltv`, `value` — optional | `START_TRIAL` |
| `SubmitApplication` | Person applies for a product/service/program | optional | `SUBMIT_APPLICATION` |
| `Subscribe` | Person starts a paid subscription | `currency`, `predicted_ltv`, `value` — optional | `SUBSCRIBE` |
| `ViewContent` | A page you care about is visited (product/landing page). Tells you someone hit the URL — not what they did there. | `content_ids`, `content_type`, `contents`, `currency`, `value` — optional; `contents`/`content_ids` required for catalog ads | `VIEW_CONTENT` |

`PageView` is also a standard event, fired automatically by the base code. Leave that call in place.

**Deduplication with the Conversions API:** if the same conversion is also sent server-side, pass a shared event ID as the fourth argument so the two aren't double-counted:

```js
fbq('track', 'Purchase', {value: 30.00, currency: 'USD'}, {eventID: 'order-1234'});
```

## Object properties

Usable on any custom event and on the standard events that support them. Always JSON.

| Key | Type | Notes |
|---|---|---|
| `content_category` | string | Category of the page/product. |
| `content_ids` | array of strings or integers | Product IDs / SKUs: `['ABC123', 'XYZ789']`. Must match catalog IDs for catalog ads. |
| `content_name` | string | Name of the page/product. |
| `content_type` | string | `'product'` or `'product_group'` — which one depends on whether the IDs you pass are product IDs or product-group IDs. Omitting it makes Meta match the event to every item sharing that ID regardless of type. Collaborative Ads accept **only** `'product'`. |
| `contents` | array of objects | `[{id: 'ABC123', quantity: 2}]`. `id` and `quantity` are both **required** on each entry — a bare `{id: ...}` is the most common malformed payload. Carries the EAN where applicable. |
| `currency` | string | ISO 4217 code — `'USD'`, `'GBP'`. Never a symbol. |
| `delivery_category` | string | `in_store` (customer collects in store), `curbside`, or `home_delivery`. |
| `num_items` | integer | Item count at checkout. Used with `InitiateCheckout`. |
| `predicted_ltv` | integer or float | Predicted lifetime value of a subscriber, as an exact value. |
| `search_string` | string | What the user typed. Used with `Search`. |
| `status` | boolean | Registration status. Used with `CompleteRegistration`. |
| `value` | integer or float | A monetary amount, as a number. **Required for `Purchase` and for any event using value optimization.** |

Custom properties are allowed alongside these — e.g. `compared_product: 'recommended-banner-shoes'`. If a key will be used to define a custom audience, it **must not contain spaces**.

## Choosing between content_ids and contents

Both identify the products involved. They are not interchangeable in every context:

- `content_ids: ['201', '301']` — simple ID list. Enough for `ViewContent` and for catalog-ad matching.
- `contents: [{id: '301', quantity: 1}, {id: '401', quantity: 2}]` — IDs **with quantities**. Required whenever quantity is meaningful: `AddToCart`, `Purchase`, and anything Collaborative Ads consumes.

Rule of thumb: if the event involves a basket, use `contents`. Product Group IDs are not supported in the Collaborative Ads `contents` field.

What `value` means shifts by event, which is easy to get subtly wrong:
- `ViewContent` → the value of the single item.
- `AddToCart` → the value of the items just added, **not** the running basket total.
- `Purchase` → the total basket value, including shipping and tax.

## Custom events

```js
fbq('trackCustom', 'ShareDiscount', {promotion: 'share_discount_10%'});
```

Names are strings, max 50 characters. They support the same parameter objects as standard events and can define custom audiences — but they don't feed the standard-event-driven optimizations, so prefer a standard event whenever one genuinely fits.

## Custom conversions

Defined in Events Manager by matching against referrer URLs — no code changes. A thank-you page at `/thank-you` becomes a conversion by rule alone. Also creatable via the API at `/{AD_ACCOUNT_ID}/customconversions` with a `pixel_rule`, then targeted from an ad set's `promoted_object`.

Limits and caveats:
- Max **100** custom conversions per ad account.
- Ads Insights does not support product-ID breakdowns or unique action counts for them.
- Since Sept 2, 2025 Meta flags custom conversions whose names imply health conditions ("arthritis", "diabetes") or financial status ("credit score", "high income"). Flagged ones return `is_unavailable: true` from the API and cannot be used in new campaigns. Fix by creating a differently-named conversion, or request a review if flagged in error. So: never name a custom conversion after a sensitive attribute.
