# GA4: Events, Ecommerce, Identifiers, Limits

## Contents

- [The data model](#the-data-model)
- [Automatically collected events](#automatically-collected-events)
- [Enhanced Measurement events](#enhanced-measurement-events)
- [Recommended events by vertical](#recommended-events-by-vertical)
- [Ecommerce events and parameters](#ecommerce-events-and-parameters)
- [The items[] spec](#the-items-spec)
- [Identifiers](#identifiers)
- [Custom dimensions — the parameter you send is not the one you can report on](#custom-dimensions--the-parameter-you-send-is-not-the-one-you-can-report-on)
- [Limits and quotas](#limits-and-quotas)
- [Measurement Protocol](#measurement-protocol)
- [BigQuery export](#bigquery-export)
- [The PII policy](#the-pii-policy)

## The data model

GA4 is **event + parameters + user properties + items[]**. There are no pageviews-as-a-special-case and no categories/actions/labels. Everything is an event with a name and up to 25 parameters, some of which GA4 adds itself.

Every GA4 event automatically carries `language`, `page_location`, `page_referrer`, `page_title`, `screen_resolution`, plus internal params (`ga_session_id`, `ga_session_number`, `engagement_time_msec`).

## Automatically collected events

Always on, cannot be disabled: `first_visit`, `session_start`, `user_engagement` (carries `engagement_time_msec`). App streams add `first_open`, `in_app_purchase`, `app_update`, `os_update`, `app_remove`, notification events.

## Enhanced Measurement events

Web stream; each toggles individually in the data stream settings.

| Event | Key parameters |
|---|---|
| `page_view` | `page_location`, `page_referrer`, `page_title` (cannot be turned off) |
| `scroll` | `percent_scrolled` (fires at 90% only) |
| `click` (outbound) | `link_classes`, `link_domain`, `link_id`, `link_url`, `outbound` |
| `view_search_results` | `search_term` |
| `video_start` / `video_progress` / `video_complete` | `video_current_time`, `video_duration`, `video_percent`, `video_provider`, `video_title`, `video_url`, `visible` |
| `file_download` | `file_extension`, `file_name`, `link_text`, `link_url` |
| `form_start` / `form_submit` | `form_id`, `form_name`, `form_destination`, `form_submit_text` |

Two traps:

- **Enhanced Measurement double-counts in SPAs.** If you push your own `virtual_page_view` and leave Enhanced Measurement's page_view on with history-change detection, every route change counts twice. Set `send_page_view: false` on the Google tag when you own pageviews.
- These parameters are **collected but invisible** until registered as event-scoped custom dimensions. `percent_scrolled` and `form_id` exist in the payload and in no report.

## Recommended events by vertical

Recommended events require exact spelling and are **not** collected automatically — sending `signup` instead of `sign_up` gets you a custom event with none of the built-in reporting.

- **All properties:** `ad_impression`, `earn_virtual_currency`, `spend_virtual_currency`, `generate_lead`, `join_group`, `login`, `purchase`, `refund`, `search`, `select_content`, `share`, `sign_up`, `tutorial_begin`, `tutorial_complete`, `unlock_achievement`, `level_up`, `post_score`, `view_item`
- **Retail/ecommerce** (also used by education, real estate, travel): the ecommerce set below
- **Lead generation** (B2B, automotive, insurance): `generate_lead`, `qualify_lead`, `disqualify_lead`, `working_lead`, `close_convert_lead`, `close_unconvert_lead` — these populate the Lead acquisition report
- **Games:** `level_start`, `level_end`, `level_up`, `post_score`, `unlock_achievement`, `earn_virtual_currency`, `spend_virtual_currency`, `tutorial_begin`, `tutorial_complete`
- **Travel/hotel:** ecommerce events plus promotion events; use `google_business_vertical` on items

## Ecommerce events and parameters

| Event | Event-level parameters |
|---|---|
| `view_item_list` | `item_list_id`, `item_list_name`, `items[]` |
| `select_item` | `item_list_id`, `item_list_name`, `items[]` |
| `view_item` | `currency`, `value`, `items[]` |
| `add_to_cart` | `currency`, `value`, `items[]` |
| `remove_from_cart` | `currency`, `value`, `items[]` |
| `view_cart` | `currency`, `value`, `items[]` |
| `add_to_wishlist` | `currency`, `value`, `items[]` |
| `begin_checkout` | `currency`, `value`, `coupon`, `items[]` |
| `add_shipping_info` | `currency`, `value`, `coupon`, `shipping_tier`, `items[]` |
| `add_payment_info` | `currency`, `value`, `coupon`, `payment_type`, `items[]` |
| `purchase` | **`transaction_id` (required)**, `currency` + `value` (required for revenue), `tax`, `shipping`, `coupon`, `affiliation`, `items[]` |
| `refund` | **`transaction_id` (required)**, `currency`, `value`, `tax`, `shipping`, `items[]` (for partial refunds) |
| `view_promotion` / `select_promotion` | `promotion_id`, `promotion_name`, `creative_name`, `creative_slot`, `location_id`, `items[]` |
| `generate_lead` | `currency`, `value` |

`currency` is required whenever `value` is set. Omit it and GA4 assumes the property's reporting currency — revenue silently lands in the wrong denomination rather than erroring.

## The items[] spec

At least one of `item_id` / `item_name` is required per item. Up to **200 items per event**.

`item_id`, `item_name`, `affiliation`, `coupon`, `discount`, `index`, `item_brand`, `item_category`, `item_category2`, `item_category3`, `item_category4`, `item_category5`, `item_list_id`, `item_list_name`, `item_variant`, `location_id`, `price`, `quantity`, plus (item-scoped where relevant) `promotion_id`, `promotion_name`, `creative_name`, `creative_slot`, and `google_business_vertical`.

- You may add up to **27 custom parameters per item**, of which **10** (standard) / **25** (360) can be registered as item-scoped custom dimensions.
- **Item-level parameters take precedence over event-level ones.** An `item_list_name` on the item wins over the event's.
- Item-scoped custom parameters were historically absent from the BigQuery export until the `items.item_params` nested field was added (Oct 2023).

## Identifiers

| Identifier | Source / notes |
|---|---|
| `client_id` | From the `_ga` first-party cookie (`GA1.2.XXXXXXX.TIMESTAMP`); identifies a browser/device. In sGTM can be replaced by server-managed **FPID**. |
| `user_id` | Your own cross-device login ID, set explicitly. Enables the User-ID reporting identity. Must not be PII. |
| `session_id` (`ga_session_id`) / `ga_session_number` | Session identifiers. |
| App Instance ID | App equivalent of client_id (`app_instance_id`), used for Measurement Protocol app events. |
| **User-Provided Data (UPD)** | Hashed (SHA-256) `sha256_email_address`, `sha256_phone_number`, and address components. Feeds **Enhanced Conversions** and Customer Match. Enable in Admin → User-ID and user-provided data collection. **gtag/GTM hash automatically — send plaintext.** Measurement Protocol requires you to hash yourself. |
| User properties | User-scoped attributes (`membership_tier`) set via `user_properties`; become user-scoped custom dimensions. |
| Ad click IDs | `gclid`, `gbraid`, `wbraid` — captured via auto-tagging / Conversion Linker into `_gcl_*` cookies. |
| Google Signals | Cross-device data from signed-in Google users who opted into Ads Personalization. An advertising feature — consent-sensitive. |

**Enhanced Conversions email normalization** (when you hash yourself, i.e. Measurement Protocol only): trim, lowercase; for `gmail.com`/`googlemail.com` remove dots and `+` suffixes from the local part; phone in E.164; hex SHA-256.

GA4 removed UPD as a **reporting-identity** option — it is used only for conversion enhancement and audience expansion, never for user counting.

## Custom dimensions — the parameter you send is not the one you can report on

The most expensive silent failure in GA4, because the implementation looks finished.

You send `form_name: 'demo_modal'`. GA4 accepts it. DebugView shows it. It appears in **zero** reports until you register it as a custom dimension in Admin → Custom definitions. And:

- **Registration is not retroactive.** Data collected before you registered is unreachable. Forever.
- It takes **24–48 hours** to populate after registering.
- Deleting a custom dimension requires a **48-hour wait** before the name can be re-added.

So register as you instrument, not after the first report request. And budget the quota — it's small and you cannot buy more on a standard property.

**Cardinality:** high-cardinality dimensions bucket into `(other)`. Registering a user ID, a timestamp, or a full URL as a custom dimension makes the report useless and burns a slot.

## Limits and quotas

Standard property (360 in parentheses):

| Limit | Value |
|---|---|
| Event-scoped custom dimensions | **50** (125) |
| User-scoped custom dimensions | **25** (100) |
| Item-scoped custom dimensions | **10** (25) |
| Custom metrics | **50** (125) |
| Parameters per event | **25** — includes automatically collected ones (~20 usable) |
| Unique event names | 500 (app streams); unlimited (web) |
| Event name length | 40 chars, letters/numbers/underscores, case-sensitive |
| Parameter name length | 40 chars |
| Parameter value length | **100 chars** — `page_location` 1,000, `page_referrer` 420, `page_title` 300 |
| Key events (formerly conversions) | 30 per property |
| Items per event | 200 |
| User data retention | Default **2 months**, extendable to 14 |

360 does **not** raise the character limits. A 150-char product name is truncated at 100 on both tiers.

## Measurement Protocol

- Endpoint: `POST https://www.google-analytics.com/mp/collect` (EU: `region1.google-analytics.com`)
- Query params: `api_secret` (created per data stream in Admin — **server-side only, never ship it to a browser**) + `measurement_id` (web) or `firebase_app_id` (app)
- Body: `client_id` (required for web) or `app_instance_id`, optional `user_id`, `timestamp_micros` (backdate up to ~72h), `user_properties`, `user_data` (hashed UPD — **you hash here**), `consent` (`ad_user_data`, `ad_personalization`), and an `events` array (up to 25 events, each `name` + `params`)

Limitations that make MP a poor debugging target:

- **No error is returned for a malformed or incorrect payload.** A 2xx means "received", not "accepted". Use the validation endpoint during development.
- **Cannot create new users** — needs an existing `client_id` from prior browser tagging.
- **Cannot send geographic info directly.** GA4 joins geo from prior tagging via `client_id`.
- `advertising_id` not supported.
- For engagement/session reporting, include `session_id` and `engagement_time_msec` or the event lands outside any session.

Google now points at the Data Manager API for future server-to-server ingestion; MP is not deprecated.

## BigQuery export

The export is the only place you see the complete event record, and the only reliable way to reconcile UI discrepancies.

- **Event:** `event_date`, `event_timestamp`, `event_name`, `event_params` (repeated key→value with string/int/float/double subfields), `event_previous_timestamp`, `event_value_in_usd`, `event_bundle_sequence_id`
- **User:** `user_id`, `user_pseudo_id` (client_id / app instance id), `user_first_touch_timestamp`, `user_properties`, `user_ltv`
- **Device:** `device.category`, `mobile_brand_name`, `operating_system`, `os_version`, `language`, `browser`, `web_info.hostname`
- **Geo:** `geo.continent`, `country`, `region`, `city`, `metro`
- **Traffic (three distinct records):** `traffic_source` (first-touch user acquisition; not in intraday), `collected_traffic_source` (event-level UTM + click IDs incl. `gclid`, `dclid`, `srsltid` — added June 2023), `session_traffic_source_last_click` (last-click session attribution with nested `google_ads_campaign`, `sa360_campaign`, `dv360_campaign`, `cm360_campaign`, `manual_campaign` — added July 2024)
- **Ecommerce:** `ecommerce` record + `items` (repeated, with nested `item_params`)
- **Privacy:** `privacy_info.analytics_storage`, `privacy_info.ads_storage`, `privacy_info.uses_transient_token`
- **Platform/stream:** `platform`, `stream_id`, `is_active_user`

Two things worth knowing before you trust a BigQuery/UI comparison:

- When `analytics_storage` is **denied**, `user_pseudo_id` and `ga_session_id` are **stripped** — you get orphaned rows.
- **Behavioral modeling fills GA4 UI gaps but modeled data is not exported to BigQuery.** The UI and the export are *supposed* to disagree under consent denial. That gap is not a bug to chase.

## The PII policy

Google's terms prohibit sending data Google could use to identify an individual, in **event parameters, user properties, or user IDs**. No email addresses, names, phone numbers, or precise street addresses — and this explicitly includes **PII appearing in `page_location` / URLs**, which is the way it usually happens: a password-reset or checkout URL with `?email=` in the query string, captured automatically by every page_view.

The **only** sanctioned channel for personal identifiers is hashed **User-Provided Data** for Enhanced Conversions / Customer Match, which goes through the dedicated UPD pipeline.

Sending prohibited PII risks **data deletion and account action** — Google deletes the affected data range, which is unrecoverable.

If your URLs can contain PII, strip it before it reaches GA4: a `page_location` override variable in the container, or a transformation in sGTM. Do it at instrumentation time; you cannot clean it retroactively.

Advertising Features (Google Signals, remarketing, demographics) require additional policy compliance and are governed by `ad_user_data` / `ad_personalization`.
