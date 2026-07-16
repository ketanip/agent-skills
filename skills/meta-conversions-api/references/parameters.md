# Parameters

The full field matrix for `POST https://graph.facebook.com/{API_VERSION}/{PIXEL_ID}/events`.
Normalization and hashing rules for `user_data` live in `normalization.md`.

## Main body

| Parameter | Notes |
|---|---|
| `data` — array<object> | **Required.** The server event objects. Up to **1,000** per request. |
| `test_event_code` — string | **Optional.** Routes events to Events Manager → Test Events. Testing only — *"You need to remove it when sending your production payload."* Events sent with it are **not dropped**: they flow into Events Manager and are used for targeting and ads measurement. |

`access_token` is sent as a query parameter or a body field.

## Server event

| Parameter | Required | Notes |
|---|---|---|
| `event_name` | **Yes** | Standard or custom event name. Half of the dedup key. |
| `event_time` | **Yes** | Unix seconds, GMT, **transaction** time. Up to 7 days old; a single violation fails the whole request. |
| `user_data` | **Yes** | Customer information. At least one parameter required. See `normalization.md`. |
| `action_source` | **Yes** | Where the conversion happened. You warrant it is accurate. |
| `custom_data` | Optional | Business data about the event — see [Standard parameters](#custom_data--standard-parameters). |
| `event_source_url` | Optional* | Browser URL where the event happened; should match the verified domain. ***Required for website events.*** |
| `event_id` | Optional* | Unique string. *"While `event_id` is marked optional, it is recommended for event deduplication."* Effectively required in a redundant setup. |
| `opt_out` | Optional | `true` = use for attribution only, not ads delivery optimization. |
| `referrer_url` | Optional | The HTTP referrer header observed by the page that triggered the event. **Distinct from `event_source_url`** — do not put the referrer there. |
| `customer_segmentation` | Optional | Enum, see [below](#customer_segmentation). |
| `original_event_data` | Optional | For "delayed" events — see [below](#original_event_data). |
| `data_processing_options` | Optional | `["LDU"]` or `[]`. See [LDU](#limited-data-use). |
| `data_processing_options_country` | Conditional | Required with `LDU`. `1` = USA, `0` = geolocate. |
| `data_processing_options_state` | Conditional | `1000` = California, `0` = geolocate. Required with `LDU` when no IP is provided; if you set a country you must set a state. |
| `app_data` | App events | Container for app/device info. `extinfo` is a sub-parameter. |

### `action_source`

Required, and a factual assertion: *"By using the Conversions API, you agree that the `action_source`
parameter is accurate to the best of your knowledge."*

| Value | Meaning |
|---|---|
| `website` | Conversion made on your website |
| `email` | Conversion happened over email |
| `app` | Conversion made in your mobile app |
| `phone_call` | Conversion made over the phone |
| `chat` | Messaging app, SMS, or online messaging feature |
| `physical_store` | In person, at your physical store |
| `system_generated` | Automatic, e.g. an auto-pay subscription renewal |
| `business_messaging` | From ads that click to Messenger, Instagram, or WhatsApp |
| `other` | Not listed above |

*"All action source values enable ad measurement and custom audience creation capabilities. All
action sources enable ad optimization capabilities."*

### Required-parameter summary

- **Website events:** `client_user_agent`, `action_source`, `event_source_url` — plus the always-
  required `event_name`, `event_time`, `user_data`.
- **Non-web events:** *"require only"* `action_source`.
- **App events:** `app_data` with `advertiser_tracking_enabled` and `extinfo`.

### `customer_segmentation`

Optional enum describing the user's relationship to the business:
`new_customer_to_business`, `new_customer_to_business_line`, `new_customer_to_product_area`,
`new_customer_to_medium`, `existing_customer_to_business`, `existing_customer_to_business_line`,
`existing_customer_to_product_area`, `existing_customer_to_medium`, `customer_in_loyalty_program`.

### `original_event_data`

For associating a *delayed* event with a past acquisition event. *"We highly recommend using
`original_event_data` when there's a delay between when an event is sent and a past acquisition event
it should be associated with."* Fields, all optional: `event_name`, `event_time`, `order_id`,
`event_id`.

## `user_data` — hash / do-not-hash

Full normalization rules and Meta's verified SHA-256 vectors: `normalization.md`.

| Parameter | Hashing | Meaning |
|---|---|---|
| `em` | **Required** | Email |
| `ph` | **Required** | Phone number (with country code, wihtout + sign remove it before hashing) |
| `fn` / `ln` | **Required** | First / last name |
| `ge` | **Required** | Gender (`f` / `m`) |
| `db` | **Required** | Date of birth (`YYYYMMDD`) |
| `ct` | **Required** | City |
| `st` | **Required** | State (2-char ANSI, lowercase) |
| `zp` | **Required** | Zip code |
| `country` | **Required** | ISO 3166-1 alpha-2, lowercase |
| `external_id` | **Recommended** | Your own user/loyalty/cookie ID — consistency across channels is mandatory |
| `client_ip_address` | **Do not hash** | Customer's IPv4/IPv6. *"must never be hashed"* |
| `client_user_agent` | **Do not hash** | Customer's UA. **Required for website events** |
| `fbc` | **Do not hash** | Click ID from `_fbc` / `fbclid` |
| `fbp` | **Do not hash** | Browser ID from `_fbp` |
| `subscription_id` | **Do not hash** | Subscription ID for this transaction |
| `fb_login_id` | **Do not hash** | App-scoped ID issued at first login |
| `lead_id` | **Do not hash** | ID of a Meta Lead Ads lead |
| `anon_id` | **Do not hash** | Install ID — *app events only* |
| `madid` | Do not hash | Mobile advertiser ID (Android AAID / Apple IDFA) — *app events only* |
| `page_id` | **Do not hash** | Page ID associated with the event/bot |
| `page_scoped_user_id` | **Do not hash** | Page-scoped user ID from your webhook |
| `ctwa_clid` | **Do not hash** | Click-to-WhatsApp click ID |
| `ig_account_id` | **Do not hash** | Instagram account ID of the business |
| `ig_sid` | **Do not hash** | Instagram-scoped user ID (IGSID) |

Sending both `client_ip_address` and `client_user_agent` on every event *"may help improve event
matching and could also help improve ad delivery."*

## `custom_data` — standard parameters

The commerce fields that matter most:

| Parameter | Notes |
|---|---|
| `value` | **Required for purchase events** or any event using value optimization. *"A numeric value… must represent a monetary amount."* |
| `currency` | **Required for purchase events.** A valid ISO 4217 three-digit code. |
| `content_ids` | Content IDs — e.g. product SKUs for `AddToCart`. |
| `contents` | List of JSON objects with product IDs plus info. Available fields: `id`, `quantity`, `item_price`, `delivery_category`. |
| `content_type` | `product` or `product_group`. Use `product_group` when `content_ids` are groups distinguishing variants (color, size, …). |
| `order_id` | The order ID for the transaction, as a string. |
| `num_items` | **`InitiateCheckout` only.** Items the user tries to buy. |
| `search_string` | **`Search` only.** |
| `delivery_category` | Optional for purchases: `in_store`, `curbside`, `home_delivery`. |
| `predicted_ltv` | Predicted lifetime value of a conversion event. |
| `net_revenue` | Margin value of a conversion event. |

For catalog ads, `content_ids`/`contents` IDs must match the catalog's product IDs exactly.

The full table also covers travel (`checkin_date`, `origin_airport`, `travel_class`, …), automotive
(`make`, `model`, `vin`, `body_style`, `fuel_type`, `transmission`, …), and real estate
(`listing_type`, `property_type`, `preferred_beds_range`, …) verticals, each with website /
app (`fb_`-prefixed) / offline column variants — see the
[Standard Parameters page](https://developers.facebook.com/documentation/ads-commerce/conversions-api/parameters/custom-data).

> **Note on `value` type.** The docs say "numeric value" and the canonical examples send a JSON number
> (`"value": 100.2`), though one example on the fbc/fbp page shows a quoted string (`"value":
> "142.52"`). Send a number. The docs do not state what happens to a string, so don't assume it is
> accepted — and never send a locale-formatted string like `"5.000,00"`.

## Beyond web

### App events — `app_data`

| Parameter | Notes |
|---|---|
| `advertiser_tracking_enabled` | **Required.** ATT permission on iOS 14.5+. `0` disabled, `1` enabled. |
| `application_tracking_enabled` | Optional. App-level opt-out choice. `0` / `1`. |
| `extinfo` | **Required.** Extended device info. |
| `campaign_ids`, `install_referrer`, `installer_package`, `url_schemes`, `vendor_id`, `windows_attribution_id` | Optional. |

`extinfo` is a **positional array — "all values are required and must be in the order indexed below.
If a value is missing, fill with an empty string as a placeholder."** Index `0` is the version: `i2`
for iOS, `a2` for Android. Then: `1` app package name, `2` short version, `3` long version, `4` OS
version *(required)*, `5` device model, `6` locale, `7` timezone abbreviation, `8` carrier, `9`
screen width, `10` screen height, `11` screen density, `12` CPU cores, `13` external storage GB, `14`
free external storage GB, `15` device timezone.

See [Conversions API for App Events](https://developers.facebook.com/documentation/ads-commerce/conversions-api/app-events).

### Offline / physical store

`action_source: "physical_store"`. Upload transactions **within 62 days** of the conversion (not 7).
See [Sending Offline Events](https://developers.facebook.com/documentation/ads-commerce/conversions-api/offline-events).

### Business messaging

`action_source: "business_messaging"`, with `page_id`, `page_scoped_user_id`, `ctwa_clid`, `ig_sid`
as relevant. See the
[Business Messaging onboarding guide](https://developers.facebook.com/documentation/ads-commerce/conversions-api/business-messaging).

## Limited Data Use

LDU is per-event, set inside each object in `data`.

```json
{"data": [{"...": "...", "data_processing_options": ["LDU"],
           "data_processing_options_country": 0, "data_processing_options_state": 0}]}
```

- `["LDU"]` with country `0` / state `0` → Meta geolocates the event (needs `client_ip_address`).
- `["LDU"]` with country `1` / state `1000` → explicitly California.
- `[]` or omitting the field → explicitly *not* processed under LDU restrictions.
- If you set a country you must set a state, or geolocation logic applies to the whole event.
- `data_processing_options_state` is required if you send `LDU` and provide no IP address.

See [Data Processing Options](https://developers.facebook.com/documentation/ads-commerce/marketing-api/overview/data-processing-options).

## Access tokens and terms

**Direct integration** (the common case): generate the token in Events Manager → your Pixel →
Settings → Conversions API → *Generate access token* (visible only to users with developer privileges
for the business). Then Overview → Manage Integrations → Manage, which auto-creates the CAPI app and
system user. *"There is no need to go through App Review or request any permissions."* Tokens created
from v12.0 onward work with all available Graph API versions.

**As a platform** (sending on behalf of clients) is the *only* path that needs App Review, with
Advanced Access, the Marketing API Access Tier feature, and `ads_management`, `pages_read_engagement`,
`ads_read`. Don't apply these requirements to a direct integration. See
[Set up Conversions API as a Platform](https://developers.facebook.com/documentation/ads-commerce/conversions-api/set-up-conversions-api-as-a-platform).

Prerequisites also include *"appropriate notice to and consent from your users for the sharing of
event data with Facebook, as required by the [Facebook Business Tools Terms](https://www.facebook.com/legal/technology_terms)."*
Hashing is a transport requirement — it is not consent, and it does not substitute for a lawful
basis. Gate sends on your consent state, and use LDU where CCPA applies.

## Versioning

CAPI is built on the Marketing API, itself on the Graph API. The release cycle follows the Graph API,
and *"every version is supported for at least two years. This exception is only valid for the
Conversions API."* Meta's current examples use `v25.0`. Pin a version, and treat bumps as scheduled
work.
