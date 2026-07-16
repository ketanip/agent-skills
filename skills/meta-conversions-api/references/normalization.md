# Normalization and Hashing

The rule that governs everything on this page: **CAPI does not hash for you.** The browser Pixel's
advanced matching hashes client-side; here you normalize, SHA-256, and send lowercase hex. Meta's
systems *"are designed to not accept customer information that is unhashed Contact Information."*
The Business SDKs hash for you — if you use one, do not double-hash.

A hash of a wrongly-normalized value is still a valid hash. It is accepted, it matches nobody, and
you get `200 events_received: 1`. There is no feedback loop. This is why the rules below are worth
following exactly rather than approximately.

## The two lists

**Hash these (normalize first):** `em`, `ph`, `fn`, `ln`, `ge`, `db`, `ct`, `st`, `zp`, `country`.

**Hashing recommended:** `external_id`.

**Never hash these:** `client_ip_address`, `client_user_agent`, `fbc`, `fbp`, `subscription_id`,
`fb_login_id`, `lead_id`, `anon_id`, `madid`, `page_id`, `page_scoped_user_id`, `ctwa_clid`,
`ig_account_id`, `ig_sid`.

You must provide **at least one** `user_data` parameter, correctly formatted.

## Per-field rules, with Meta's published vectors

Every digest below is quoted from Meta's documentation and independently verified as
`SHA-256(UTF-8(normalized))`. Use them as test fixtures — if your normalizer reproduces these seven,
it is correct.

### `em` — Email
Trim leading/trailing spaces. Lowercase everything.

| Input | Normalized | SHA-256 |
|---|---|---|
| `John_Smith@gmail.com` | `john_smith@gmail.com` | `62a14e44f765419d10fea99367361a727c12365e2520f32218d505ed9aa0f62f` |

### `ph` — Phone Number
Remove symbols, letters, and **any leading zeros**. Must include the country code — *"Always include
the country code as part of your customers' phone numbers, even if all of your data is from the same
country."* A number without a country code will not match.

| Input | Normalized | SHA-256 |
|---|---|---|
| `(650)555-1212` (US) | `16505551212` | `e323ec626319ca94ee8bff2e4c87cf613be6ea19919ed1364124e16807ab3176` |

### `fn` / `ln` — First / Last Name
Lowercase, no punctuation. Roman a–z recommended, **but special characters are explicitly supported**
— they must be UTF-8 encoded, not stripped.

| Input | Normalized | SHA-256 |
|---|---|---|
| `Mary` | `mary` | `6915771be1c5aa0c886870b6951b03d7eafc121fea0e80a5ea83beb7c449f4ec` |
| `정` | `정` | `8fa8cd9c440be61d0151429310034083132b35975c4bea67fdd74158eb51db14` |
| `Valéry` | `valéry` | `08e1996b5dd49e62a4b4c010d44e4345592a863bb9f8e3976219bac29417149c` |

> The `정` and `valéry` vectors exist precisely because the tempting implementation —
> `name.toLowerCase().replace(/[^a-z]/g, '')` — is wrong. It yields `""` for `정` and `valry` for
> `Valéry`. Both hash cleanly and match nothing. Keep the characters; encode UTF-8.

### `db` — Date of Birth
`YYYYMMDD`. Year 1900–current, month `01`–`12`, day `01`–`31`. Input may carry punctuation; the
normalized form does not.

| Input | Normalized | SHA-256 |
|---|---|---|
| `2/16/1997` | `19970216` | `01acdbf6ec7b4f478a225f1a246e5d6767eeab1a7ffa17f025265b5b94f40f0c` |

### `ge` — Gender
A single lowercase initial: `f` or `m`.

### `ct` — City
Lowercase, no punctuation, no special characters, **no spaces**. UTF-8 if special characters are
used. Examples: `paris`, `london`, `newyork`.

### `st` — State
The **2-character ANSI abbreviation, lowercase** (`az`, `ca`) — not the full state name. Non-US
states: lowercase, no punctuation, no special characters, no spaces.

### `zp` — Zip Code
Lowercase, no spaces, no dash. **First 5 digits for US zip codes only.**

| Country | Example |
|---|---|
| US | `94035` (first 5 digits) |
| Australia | `1987` |
| France | `75018` |
| UK | `m11ae` (area/district/sector format) |

> Truncating to 5 characters unconditionally is a bug: it is a US-specific rule. A UK postcode like
> `SW1A 1AA` normalizes to `sw1a1aa`, not `sw1a1`.

### `country` — Country
Lowercase [ISO 3166-1 alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2). *"Always include
your customers' countries even if all of your country codes are from the same country. We match on a
global scale."*

| Input | Normalized | SHA-256 |
|---|---|---|
| `United States` | `us` | `79adb2a2fce5c6ba215fe5f27f532d4e7edbac4b6a5e09e1ef3a08084a904621` |

### `external_id`
Any unique ID from your system — loyalty ID, user ID, external cookie ID. Hashing recommended; you
may send one or more per event.

The binding constraint is **consistency, not hashing**: *"if you send a browser Pixel event with
`external_id` set to `123`, your Conversions API event for that same user should also have
`external_id` set to `123`."* Hashed on one channel and raw on the other = no join. Pick one form and
apply it everywhere, including OCAPI and app events.

Why it's worth wiring up: once Meta matches an `external_id` to a user via *any* channel, later
events can carry `external_id` alone and still match. Matches expire periodically — refresh often.
If you send `fbp` but no `external_id`, Meta uses `fbp` as the external ID; if you send both,
`external_id` wins.

## `fbc` and `fbp` — never hashed, strictly formatted

Send both whenever available; refresh with the latest values, as they change across sessions.

### `fbc` — the Click ID

Format: `fb.${subdomainIndex}.${creationTime}.${fbclid}`

- `fb` — literal prefix.
- `subdomainIndex` — `com` = 0, `example.com` = 1, `www.example.com` = 2. **Generating server-side
  without saving an `_fbc` cookie? Use `1`.**
- `creationTime` — Unix epoch in **milliseconds** (not seconds) when `_fbc` was stored; if you don't
  store the cookie, when you first observed the `fbclid`.
- `fbclid` — the raw query-parameter value. **Case sensitive — do not modify case.**

```
fb.1.1554763741205.IwAR2F4-dbP0l7Mn1IawQQGCINEz7PYXQvwjNwB_qa2ofrHyiLjcbCRxTDMgk
```

Two legitimate sources: the `_fbc` cookie (set automatically when the Pixel is installed), or the
`fbclid` URL query parameter, which lets you send `fbc` even with **no Pixel on the site**. Reading
`fbclid` server-side and formatting it yourself is the supported path.

**Do not invent an `fbc` when you have neither.** A placeholder such as
`` `fb.1.${Date.now()}.unknown` `` is not a click ID: it cannot match, and it manufactures a fake
ad-click attribution record for every organic and direct conversion. Omit the field. An absent field
is handled; a fabricated one is worse than nothing.

Recommended storage: set `_fbc` as an HTTP cookie with a **90-day** expiry — but only if the cookie
doesn't exist and you got a `fbclid`, or the URL's `fbclid` differs from the one in the cookie (the
part after the last `.`). Server-side storage is an equivalent alternative.

### `fbp` — the Browser ID

Format: `fb.${subdomainIndex}.${creationTime}.${randomNumber}` — same prefix and subdomain-index
rules, `creationTime` again in **milliseconds**, and a random number the Pixel SDK generates for
uniqueness.

```
fb.1.1596403881668.1116446470
```

Written by the Pixel to the `_fbp` cookie when it's installed and using first-party cookies. Read the
cookie; pass it through untouched.

## Where the values have to come from

`client_ip_address`, `client_user_agent`, `fbc`, and `fbp` describe *the customer's browser*. The
docs note these are added automatically for browser events but *"must be manually configured for
events sent through the server."*

So they must be captured during the customer's own HTTP request. If you fire CAPI from a payment
webhook, a queue worker, or a cron job, there is no such request in scope — you would be sending your
worker's IP and your HTTP client's user agent, which is worse than omitting them. Capture IP, UA,
`_fbp`, and `_fbc` at checkout, persist them on the order, and pass them into the deferred job along
with the real `event_time`.

`client_ip_address` must be a valid IPv4 or IPv6 address with no spaces (IPv6 preferred where
available). Behind a proxy, that's the client end of `X-Forwarded-For`, not the socket address.
`client_user_agent` is **required for website events**.

## Implementation notes

- **Never hash an empty string.** `sha256("")` is a constant, valid-looking digest. Drop the field
  when the source value is empty.
- `em`, `ph`, `fn`, `ln`, `ge`, `db`, `ct`, `st`, `zp`, `country`, `external_id` accept a string *or
  a list of strings* — send multiple when a user has several (two emails, two phones).
- Apply the same customer-information parameters on both channels: *"make sure to apply the same set
  of customer information parameters your system is currently sharing to the browser side to the
  server side."*
- Graph API **v13.0+ added requirements around which combinations of customer information parameters
  are valid.** The parameters page points to the best-practices "baseline requirements for matching"
  page for the current combination rules; that page is outside this distillation — check it before
  relying on a minimal `user_data`.
- If you use the **parameter builder library**, formats gain a trailing appendix — its page governs,
  not this one.
