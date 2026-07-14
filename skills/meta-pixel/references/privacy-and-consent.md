# Advanced Matching, Consent & Data Processing

Everything here changes what personal data leaves the browser. Get the user's explicit intent before enabling any of it — and when a site serves EU or US-state visitors, raise consent proactively rather than waiting to be asked. An implementation that is technically correct and legally non-compliant is not a correct implementation.

## Contents
- [Advanced matching](#advanced-matching)
- [GDPR cookie consent](#gdpr-cookie-consent)
- [Limited Data Use (US states)](#limited-data-use-us-states)
- [What the pixel collects by default](#what-the-pixel-collects-by-default)

## Advanced matching

Sends customer data alongside events so Meta can match more website actions to Facebook accounts — which raises attributed conversions. Pass it as the **third argument to `fbq('init')`**. Placement matters: put these values anywhere else and they are not treated as manual advanced matching.

```js
fbq('init', '283859598862258', {
  em: 'email@email.com',   // hashed automatically by the pixel with SHA-256
  fn: 'first_name',
  ln: 'last_name'
});
```

The pixel hashes these client-side, so you may pass plain lowercase values — or pre-hashed normalized SHA-256 ones. Both are accepted for email.

Normalization is not optional: an unnormalized value hashes to something Meta can't match, so the field is wasted. Format exactly as below.

| User data | Param | Format | Example |
|---|---|---|---|
| Email | `em` | lowercase, or SHA-256 of the lowercase value | `jsmith@example.com` |
| First name | `fn` | lowercase letters | `john` |
| Last name | `ln` | lowercase letters | `smith` |
| Phone | `ph` | digits only, including country and area code | `16505554444` |
| External ID | `external_id` | any unique advertiser ID (loyalty ID, user ID, cookie ID) | `a@example.com` |
| Gender | `ge` | single lowercase letter, `f` or `m`; blank if unknown | `f` |
| Birthdate | `db` | digits, year then month then day | `19910526` |
| City | `ct` | lowercase, spaces removed | `menlopark` |
| State/Province | `st` | lowercase two-letter code | `ca` |
| Zip/Postal | `zp` | string | `94025` |
| Country | `country` | lowercase two-letter code | `us` |

Advanced matching can also be enabled automatically from Events Manager, with no code. If the user just wants it on and isn't attached to doing it in code, that's the lower-risk path — mention it.

For `<img>`-tag installs, hash the values yourself with SHA-256 and pass them as `ud[...]`:

```html
<img height="1" width="1" style="display:none"
  src="https://www.facebook.com/tr/?id=PIXEL_ID&ev=Purchase
    &ud[em]=f1904cf1a9d73a55fa5de0ac823c4403ded71afd4c3248d00bdcd0866552bb79
    &ud[fn]=4ca6f6d5a544bf57c323657ad33aae1a019c775518cf4414beedb86962aea7c1
    &cd[value]=0.00
    &cd[currency]=USD" />
```

## GDPR cookie consent

GDPR applies to any company processing the personal data of people in the EU, wherever that company is based. If the site needs affirmative consent (an "I agree" banner) before tracking, gate the pixel with the consent API.

```js
// Revoke BEFORE init — pixel fires are queued, not sent
fbq('consent', 'revoke');
fbq('init', '<your pixel ID>');
fbq('track', 'PageView');
```

```js
// Once the visitor affirmatively consents
fbq('consent', 'grant');
```

Two details that are easy to miss and that break the gate entirely:

- `revoke` must be called **before** `init`, or the first events go out before the visitor has agreed.
- `revoke` must be called on **every page** — it does not persist across page loads.

If the site already handles consent through a tag manager or CMP, this code is redundant; check before adding it.

## Limited Data Use (US states)

Limited Data Use (LDU) tells Meta to process the event as a service provider/processor, limiting how the data is used. It applies to people in **California, Colorado, and Connecticut** and must be **proactively enabled** — it is off by default.

Call `dataProcessingOptions` before `fbq('init')`:

```js
// Explicitly NOT enabling LDU
fbq('dataProcessingOptions', []);
fbq('init', '{pixel_id}');
fbq('track', 'PageView');

// Enable LDU, let Meta geolocate the user
fbq('dataProcessingOptions', ['LDU'], 0, 0);

// Enable LDU with an explicit location (California)
fbq('dataProcessingOptions', ['LDU'], 1, 1000);
```

The two numbers are country and state: `0, 0` means "Meta, work it out"; `1, 1000` is the US/California pair. If LDU is enabled without location params, Meta determines whether the event came from a covered state.

For `<img>` installs the equivalents are `dpo`, `dpoco`, `dpost`:

```html
<img src="https://www.facebook.com/tr?id={pixel_id}&ev=Purchase&dpo=LDU&dpoco=1&dpost=1000" />
```

Tell the user the tradeoff rather than silently enabling it: LDU limits retargeting and measurement, and campaign performance may drop. It's a compliance decision, not a technical one.

## What the pixel collects by default

Worth stating plainly when a user asks "what does this actually send?" — several of these surprise people:

- **HTTP headers** — IP address, browser, page location, referrer.
- **Pixel-specific data** — pixel ID and the Facebook cookie.
- **Button click data** — buttons clicked, their labels, and pages reached as a result.
- **Form field names** — field *names* like `email`, `address`, `quantity`. Field **values** are not captured unless you send them yourself via advanced matching or event parameters.
- **Optional values** — whatever you pass in event parameters.

Button-click and page-metadata collection is the "automatic configuration" behavior; it can be turned off with `fbq('set', 'autoConfig', false, 'FB_PIXEL_ID')` before `init` (see `advanced.md`).
