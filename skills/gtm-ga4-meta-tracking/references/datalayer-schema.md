# Canonical dataLayer Schema & Mapping

One schema feeds both GA4 and Meta. GA4's ecommerce shape is the source of truth; the Meta tags map out of it inside the container. Designing two parallel schemas is how they drift.

## Contents

- [Rules that apply to every push](#rules-that-apply-to-every-push)
- [The full-funnel schema](#the-full-funnel-schema)
- [A note on the upper-funnel event_ids](#a-note-on-the-upper-funnel-event_ids)
- [Mapping table: dataLayer → GA4 → Meta](#mapping-table-datalayer--ga4--meta)
- [Event name mapping](#event-name-mapping)
- [Mapping items[] to Meta in the container](#mapping-items-to-meta-in-the-container)
- [SPA pushes](#spa-pushes)

## Rules that apply to every push

1. **`dataLayer.push({ ecommerce: null })` immediately before every ecommerce push.** GTM's model merges rather than replaces, so without it the previous event's `items` bleed into this one. `undefined` does not clear it — `null` does.
2. **`event_id` on every event you also send server-side**, **derived** from shared state — never generated independently on each side (see SKILL.md → the dedup contract). The IDs in the examples below are illustrative literals; read the [note on the upper-funnel IDs](#a-note-on-the-upper-funnel-event_ids) before copying their *shape*.
3. **`user_data` carries plaintext.** The GA4 UPD variable and `fbevents.js` hash at send time. Pre-hashing breaks Enhanced Conversions.
4. **Types are load-bearing.** `value` is a number, `currency` an ISO 4217 code, `item_id` a string when the catalog holds strings.
5. **Push after the fact is true.** `purchase` fires on the confirmation page from the server's response, not from optimistic UI on the checkout button.

## The full-funnel schema

```javascript
// ---------- VIEW ITEM ----------
dataLayer.push({ ecommerce: null });
dataLayer.push({
  event: 'view_item',
  event_id: 'view_item.SKU_4001.' + pageLoadId,   // browser-only — see the note below
  ecommerce: {
    currency: 'USD',
    value: 29.99,
    items: [{
      item_id: 'SKU_4001',            // must match the Meta catalog id exactly, incl. type
      item_name: 'Blue T-Shirt',
      item_brand: 'Acme',
      item_category: 'Apparel',
      item_variant: 'M / Blue',
      price: 29.99,
      quantity: 1,
      index: 0
    }]
  }
});

// ---------- ADD TO CART ----------
dataLayer.push({ ecommerce: null });
dataLayer.push({
  event: 'add_to_cart',
  event_id: 'add_to_cart.' + cartToken + '.SKU_4001.' + addedAtMs,   // see the note below
  ecommerce: {
    currency: 'USD',
    value: 59.98,                     // price * quantity, NOT the unit price
    items: [{ item_id: 'SKU_4001', item_name: 'Blue T-Shirt', price: 29.99, quantity: 2, index: 0 }]
  }
});

// ---------- BEGIN CHECKOUT ----------
dataLayer.push({ ecommerce: null });
dataLayer.push({
  event: 'begin_checkout',
  event_id: 'begin_checkout.' + cartToken,
  ecommerce: {
    currency: 'USD', value: 129.97, coupon: 'SUMMER_FUN',
    items: [ /* ... */ ]
  }
});

// ---------- PURCHASE ----------
dataLayer.push({ ecommerce: null });
dataLayer.push({
  event: 'purchase',
  event_id: 'order_10057',            // reuse the order id — both sides already have it
  user_data: {                        // plaintext; GA4/Meta tags hash at send time
    email: 'jane@example.com',
    phone_number: '+14155551234',
    address: {
      first_name: 'jane', last_name: 'doe', street: '1 Main St',
      city: 'san francisco', region: 'CA', postal_code: '94105', country: 'US'
    }
  },
  ecommerce: {
    transaction_id: 'order_10057',    // required by GA4
    currency: 'USD',                  // required for revenue
    value: 129.97,                    // required for revenue
    tax: 8.20,
    shipping: 5.00,
    coupon: 'SUMMER_FUN',
    items: [
      { item_id: 'SKU_4001', item_name: 'Blue T-Shirt', price: 29.99, quantity: 1, index: 0 },
      { item_id: 'SKU_5023', item_name: 'Grey Hoodie',  price: 49.99, quantity: 2, index: 1 }
    ]
  }
});
```

For a lead-gen funnel, the same discipline with different events:

```javascript
dataLayer.push({
  event: 'generate_lead',
  event_id: eventId,                  // minted once, ALSO sent to your API — see SKILL.md
  form_name: 'demo_modal',
  value: 250,                         // your qualified-lead estimate, for Meta bidding
  currency: 'USD',                    // NOT revenue — keep out of GA4 revenue reporting
  user_id: currentUser?.id,
  user_data: { email: values.email, phone_number: values.phone }
});
```

A lead `value` is a modeling input for Meta's bidding, **not revenue**. GA4 will happily treat a `value` + `currency` pair on `generate_lead` as monetary and roll it into revenue reporting, where it double-counts against the eventual `purchase` from the same customer.

The mechanism, since "keep it out of revenue" is not self-executing: **push it once, map it differently per vendor in the container.** The Meta tag reads `{{dlv - value}}` into `value` (bidding wants it there). The GA4 tag maps the same variable to a **differently-named parameter** — `lead_value` — registered as a custom metric:

```
Meta - Lead tag:        value    = {{dlv - value}}     currency = {{dlv - currency}}
GA4 - generate_lead:    lead_value = {{dlv - value}}   (custom metric, NOT `value`)
```

GA4's own spec does list `currency`/`value` as legitimate `generate_lead` parameters, and that's correct — use them if the number genuinely *is* revenue you want counted. For an estimated lead score, rename it. One dataLayer key, two mappings.

## A note on the upper-funnel event_ids

`purchase` is the easy case: the order ID exists on both sides, so `purchase.${order.id}` derives cleanly and dedup just works.

`view_item` and `add_to_cart` have **no natural shared key**, and that is where the rule gets abandoned. The IDs above (`view_item.SKU_4001.${pageLoadId}`) are **browser-scoped**. They are correct *only* if those events are browser-only — which is the common and perfectly reasonable setup.

The moment you add a server-side counterpart for one of them, a browser-scoped ID is exactly as broken as `crypto.randomUUID()`: the server cannot reconstruct it, so nothing dedups. At that point the browser must mint the ID and **hand it across** in the same request that triggers the server event:

```js
const eventId = 'add_to_cart.' + crypto.randomUUID();   // minted ONCE, in one place

dataLayer.push({ ecommerce: null });
dataLayer.push({ event: 'add_to_cart', event_id: eventId, ecommerce: { /* ... */ } });

await fetch('/api/cart/add', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ variantId, quantity, event_id: eventId })   // travels with the payload
});
```

The server reuses that exact string and never generates its own. `crypto.randomUUID()` is fine *here* — the point was never that randomness is forbidden, it's that **each side must not mint independently**. One mint, passed across, is the same contract as deriving from an order ID.

If you can't get the ID across the boundary, send **one** side only. Two sides without a shared ID is strictly worse than one side.

## Mapping table: dataLayer → GA4 → Meta

| dataLayer key | GA4 parameter | Meta Pixel / CAPI |
|---|---|---|
| `ecommerce.value` | `value` | `custom_data.value` |
| `ecommerce.currency` | `currency` | `custom_data.currency` |
| `ecommerce.transaction_id` | `transaction_id` | `custom_data.order_id` **+** `event_id` |
| `ecommerce.coupon` | `coupon` | — |
| `ecommerce.tax` / `.shipping` | `tax` / `shipping` | — |
| `items[].item_id` | `items[].item_id` | `content_ids[]` / `contents[].id` |
| `items[].price` | `items[].price` | `contents[].item_price` |
| `items[].quantity` | `items[].quantity` | `contents[].quantity` |
| `items[].item_name` | `items[].item_name` | `content_name` |
| `items[].item_category` | `items[].item_category` | `content_category` |
| `user_data.email` | UPD `sha256_email_address` | `user_data.em` (SHA-256) |
| `user_data.phone_number` | UPD `sha256_phone_number` | `user_data.ph` (SHA-256) |
| `user_data.address.*` | UPD address components | `user_data.fn`/`ln`/`ct`/`st`/`zp`/`country` (SHA-256) |
| `user_id` / CRM ID | `user_id` / user property | `user_data.external_id` (hash recommended) |
| `_ga` cookie | `client_id` | — |
| `_fbp` / `_fbc` cookie | — | `user_data.fbp` / `user_data.fbc` (**never hashed**) |
| IP / user agent | server sets `ip_override` / UA | `client_ip_address` / `client_user_agent` (**never hashed**) |

Note the asymmetry worth internalizing: `transaction_id` maps to **two** Meta fields, and only one of them (`event_id`) does dedup. Setting `order_id` alone does not dedup.

## Event name mapping

| dataLayer `event` | GA4 event | Meta standard event |
|---|---|---|
| `view_item_list` | `view_item_list` | — |
| `select_item` | `select_item` | — |
| `view_item` | `view_item` | `ViewContent` |
| `add_to_cart` | `add_to_cart` | `AddToCart` |
| `add_to_wishlist` | `add_to_wishlist` | `AddToWishlist` |
| `view_cart` | `view_cart` | — |
| `begin_checkout` | `begin_checkout` | `InitiateCheckout` |
| `add_shipping_info` | `add_shipping_info` | — |
| `add_payment_info` | `add_payment_info` | `AddPaymentInfo` |
| `purchase` | `purchase` | `Purchase` |
| `refund` | `refund` | — |
| `search` | `search` | `Search` |
| `sign_up` | `sign_up` | `CompleteRegistration` |
| `login` | `login` | — |
| `generate_lead` | `generate_lead` | `Lead` |
| `subscribe` | (custom) | `Subscribe` |
| `start_trial` | (custom) | `StartTrial` |

**`Purchase` vs `Subscribe` for recurring revenue** — a real fork, and "prefer a standard event" doesn't settle it because both are standard.

Default to **`Purchase`** for a paid subscription conversion. It carries `value` + `currency` + catalog semantics, and it's what value-based bidding, ROAS reporting, and Advantage+ read. `Subscribe` exists and is standard, but it is thinner on optimization surface. Use `Subscribe` in addition only if you have a reporting reason to separate new subscriptions from other purchases — and if you send both for one conversion, they need **different** `event_id`s, or Meta will dedup them against each other and you'll lose one.

Renewals are the follow-on question: a monthly rebill is a real `Purchase` server-side (from the billing webhook, `action_source: 'system_generated'`, no browser event to dedup against), but firing it as a browser event is meaningless since the user isn't there.

The names are **not** interchangeable and both platforms are case-sensitive. GA4 wants `snake_case`; Meta wants `PascalCase` from its fixed list of 17. Prefer a Meta standard event over a custom one wherever one fits — standard names unlock optimization and catalog features that custom names do not.

## Mapping items[] to Meta in the container

Two Custom JavaScript variables, and the `String()` in both is the point:

```js
// {{js - Meta content_ids}}
function () {
  var items = {{dlv - ecommerce.items}} || [];
  return items.map(function (i) { return String(i.item_id); });
}
```

```js
// {{js - Meta contents}}
function () {
  var items = {{dlv - ecommerce.items}} || [];
  return items.map(function (i) {
    return {
      id: String(i.item_id),                 // string, always
      quantity: Number(i.quantity) || 1,     // required — omitting it degrades the event
      item_price: Number(i.price) || 0
    };
  });
}
```

Normalizing one and not the other is the classic half-fix: `contents` matches, `content_ids` doesn't, and catalog ads stay broken while the payload looks reasonable in Test Events.

For the parameter-shape rules on the `fbq()` side of these tags, use the **`meta-pixel`** skill.

## The identity bootstrap

Conversion events carry `user_data`, but that only helps on the conversion itself. For a logged-in user you want identity available on **every** page: the Meta base pixel wants advanced matching at `fbq('init')`, and GA4 wants `user_id` + User-Provided Data on the config tag, not just on `purchase`.

Nothing pushes that by default. Add an identity event on app load for an already-authenticated user, and again right after login:

```js
dataLayer.push({
  event: 'user_identified',
  user_id: user.id,                                              // opaque CRM id — never the email
  user_properties: { plan: user.plan, account_type: user.type },
  user_data: { email: user.email, phone_number: user.phone }     // plaintext, as always
});
```

Wire it to a `ce - user_identified` Custom Event trigger, and use it two ways: as an additional trigger on the Meta base-pixel tag (so `fbq('init')` re-runs with advanced matching once you know who the user is), and as the source for the GA4 config tag's `user_id` and User-Provided Data fields.

`user_id` must be an opaque internal ID. An email — hashed or not — in GA4's `user_id` violates the PII policy, and as `external_id` a bare email hash is trivially reversible against any breach corpus. A UUID isn't.

On logout, clear with `null` (see below) — `undefined` leaves the previous user's identity readable by every subsequent tag.

## SPA pushes

GTM's History Change trigger fires on the URL change, which in React/Vue is *before* the new view commits its title. A `page_view` read at that moment captures the previous page's title.

Push explicitly from the router instead, after commit, and turn off the GA4 tag's `send_page_view` so it doesn't also fire its own:

```js
useEffect(() => {
  dataLayer.push({
    event: 'virtual_page_view',
    page_path: location.pathname + location.search,
    page_title: document.title
  });
}, [location]);
```

On logout, clear identity with `null`, not `undefined`:

```js
dataLayer.push({ event: 'user_logout', user_id: null, user_data: null });
```

`undefined` does not clear GTM's persisted model — the previous user's identity stays readable by every subsequent tag on the page.
