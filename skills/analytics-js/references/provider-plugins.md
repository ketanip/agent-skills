# Provider & utility plugins

Config keys for the plugins people actually reach for. The full catalog is at [getanalytics.io/plugins](https://getanalytics.io/plugins/).

Note the two naming families: official plugins are scoped `@analytics/*`; community plugins are `analytics-plugin-*`. Some older docs still show unscoped names for official plugins (`analytics-plugin-google-tag-manager`) — the scoped ones are current.

## Google Analytics 4 — `@analytics/google-analytics`

Browser. Methods: `page`, `track`, `identify`.

```js
import googleAnalytics from '@analytics/google-analytics'

googleAnalytics({
  measurementIds: ['G-abc123']
})
```

| Option | Type | Notes |
|---|---|---|
| `measurementIds` **required** | `Array<string>` | GA4 measurement IDs. **An array, even for one ID.** |
| `debug` | boolean | GA debug mode |
| `dataLayerName` | string | defaults to `ga4DataLayer` |
| `gtagName` | string | defaults to `gtag` |
| `gtagConfig` | object | `anonymize_ip`, `cookie_domain`, `cookie_expires`, `cookie_prefix`, `cookie_update`, `cookie_flags` |
| `customScriptSrc` | string | proxy the GA script |
| `nonce` | string | CSP nonce |

Two traps:

- **`measurementIds` (array), not `trackingId`.** `trackingId: 'UA-...'` is the GA3 shape. Passing it to this plugin gets you a GA4 plugin with no measurement ID, which silently sends nothing. Legacy Universal Analytics lives in a separate package, `@analytics/google-analytics-v3`, and the two can run side by side.
- **GA4 double-counts page views in SPAs.** It auto-fires page views on history changes, so your `analytics.page()` on route change becomes the second one. Fix it in GA4's admin: Data Streams → Enhanced measurement → uncheck **"Page changes based on browser history events."** No amount of code fixes this from your side.

## Google Tag Manager — `@analytics/google-tag-manager`

Browser. Methods: `page`, `track`. **No `identify`** — GTM has no user model.

```js
import googleTagManager from '@analytics/google-tag-manager'

googleTagManager({ containerId: 'GTM-123xyz' })
```

| Option | Type | Notes |
|---|---|---|
| `containerId` **required** | string | the GTM container |
| `dataLayerName` | string | defaults to `dataLayer` |
| `customScriptSrc` | string | load GTM from a custom source |
| `preview` | string | preview-mode environment |
| `auth` | string | preview-mode credentials |
| `execution` | string | script execution mode |
| `nonce` | string | CSP nonce |

The `<noscript>` iframe is not injected for you — add it by hand per container. For two containers, clone the plugin and override `name` (see `writing-plugins.md`). GTM itself must be configured to fire on page views; in an SPA that means virtual pageviews.

## Segment — `@analytics/segment`

The one provider here with **both browser and Node** support. Browser methods: `page`, `track`, `identify`, `reset`. Server: `page`, `track`, `identify`.

```js
import segmentPlugin from '@analytics/segment'

segmentPlugin({ writeKey: '123-xyz' })
```

Browser options:

| Option | Type | Notes |
|---|---|---|
| `writeKey` **required** | string | |
| `disableAnonymousTraffic` | boolean | don't load Segment for anonymous visitors |
| `customScriptSrc` | string | CDN proxy for the snippet |
| `integrations` | object | enable/disable Segment destinations |

Server options: `writeKey` (required), `disableAnonymousTraffic`, `host` (`https://api.segment.io`), `path` (`/v1/batch`), `maxRetries` (`3`), `maxEventsInBatch` (`15`), `flushInterval` (`10000`ms), `httpRequestTimeout` (`10000`ms), `disable` (`false` — noOps everything), `httpClient`.

Segment's `group()` isn't in the analytics-js core API, so it's exposed as a custom method:

```js
analytics.plugins.segment.group(groupId, [traits], [options], [callback])
```

Page name defaults to `document.title`.

## Mixpanel — `@analytics/mixpanel`

Browser. Methods: `page`, `track`, `identify`, `reset`.

```js
import mixpanelPlugin from '@analytics/mixpanel'

mixpanelPlugin({ token: 'abcdef123' })
```

| Option | Type | Notes |
|---|---|---|
| `token` **required** | string | Mixpanel project token |
| `options` | object | passed to mixpanel-js init |
| `pageEvent` | string | event name for `page()` calls; defaults to the page path |
| `customScriptSrc` | string | |

## Do Not Track — `analytics-plugin-do-not-track`

NoOps everything when the browser's DNT setting is on, by returning `abort()` from the four `*Start` hooks. No config.

```js
import doNotTrack from 'analytics-plugin-do-not-track'

plugins: [ doNotTrack() ]
```

It also exports a standalone predicate, useful for gating a plugin's `enabled` flag:

```js
import { doNotTrackEnabled } from 'analytics-plugin-do-not-track'

const dontTrack = doNotTrackEnabled()

plugins: [
  googleAnalytics({
    measurementIds: ['G-abc123'],
    enabled: !dontTrack       // never even loads the script
  })
]
```

The `enabled: false` route is the stronger one: it skips `initialize` entirely, so no third-party JS is injected at all. `abort` merely stops the calls from a script that already loaded.

## Event validation — `analytics-plugin-event-validation`

Enforces a `context:object_action` naming convention (`app:user_signup`, `site:newsletter_subscribed`). Aborts anything that doesn't match.

```js
import eventValidation from 'analytics-plugin-event-validation'

eventValidation({
  context: 'app',                       // the current application
  objects: ['sites', 'user', 'widget']  // allowed object names
})
```

**List it before your provider plugins** or it validates nothing that matters.

## Original source — `analytics-plugin-original-source`

Records where a visitor originally came from, before attribution gets overwritten by later visits. No config.

```js
import originalSource from 'analytics-plugin-original-source'

plugins: [ originalSource() ]
```

Writes two localStorage keys:

- `__user_original_source` — `"source=(direct)|medium=(none)|campaign=(not set)"`
- `__user_original_landing_page` — the first landing URL

## Others in the catalog

`@analytics/amplitude`, `@analytics/customerio`, `@analytics/fullstory`, `@analytics/hubspot`, `@analytics/intercom`, `@analytics/snowplow`, `@analytics/crazy-egg`, `@analytics/perfumejs`, `@analytics/simple-analytics`, `@analytics/aws-pinpoint`, `@analytics/countly`, `@analytics/gosquared`, `@analytics/ownstats`, plus `@analytics/original-source` and request/tab/window-event plugins. Same shape throughout: import, invoke with config, drop into `plugins`.

If nothing fits, write one — it's an object with a `name`. See `writing-plugins.md`.
