---
name: analytics-js
description: Implement, debug, and extend analytics tracking with analytics-js (getanalytics.io) — the vendor-agnostic `Analytics({...})` instance, track/page/identify calls, the lifecycle hook system, writing and extending plugins, SPA page views, consent gating, and the @analytics/* util packages. Use this skill whenever the user mentions analytics-js, getanalytics.io, `Analytics({ plugins: [...] })`, `analytics.track`/`analytics.page`/`analytics.identify`, `use-analytics`, an `@analytics/*` package, or a plugin for Google Analytics, GTM, Segment, Mixpanel, Amplitude, Customer.io, HubSpot, or FullStory — and also when they ask to "add analytics", "track events", "swap analytics providers", "send events to multiple tools", or wire up page-view tracking in a React/Next/Vue SPA, even if they never name the library. Also use when reviewing existing analytics-js code, since malformed plugins and missing lifecycle hooks drop events silently.
---

# analytics-js

A vendor-agnostic analytics abstraction. You create **one instance**, register **plugins** for each destination, and call `track` / `page` / `identify` once — the instance fans each call out to every plugin. Swapping Mixpanel for Amplitude becomes a change in one array instead of a change at every call site.

The thing that makes it powerful is the same thing that makes it fail quietly: **everything is a lifecycle event, and plugins are plain objects that hook them.** A plugin missing a `loaded()` check, an abort that isn't returned, an enricher registered after the provider it meant to enrich — none of these throw. Events just don't arrive, and only in production, and usually only for the visitors who leave fastest.

## Start here: what is being asked?

| Situation | Go to |
|---|---|
| Not installed yet / new setup | [Set up the instance](#set-up-the-instance) |
| Send an event, page view, or identify | [Track an event](#track-an-event) |
| Route one call to specific destinations only | [Track an event](#track-an-event) → `options.plugins` |
| Add Google Analytics, GTM, Segment, Mixpanel, … | `references/provider-plugins.md` — config keys per provider |
| Write a custom plugin, or change what a provider receives | `references/writing-plugins.md` |
| Hook a lifecycle event, enrich payloads, validate/abort events | `references/lifecycle-and-hooks.md` |
| Page views in React / Next / Vue / any SPA | `references/frameworks-and-spa.md` — **and GA4 double-counts unless you also turn off its enhanced measurement** |
| GDPR / cookie consent / do-not-track | [Consent gating](#consent-gating) |
| UTM / campaign parameters | `references/frameworks-and-spa.md` → Campaign |
| Storage, cookies, forms, scroll depth, idle time, batching | `references/utils.md` |
| Events aren't showing up | [Verify before you call it done](#verify-before-you-call-it-done) |
| Full method signatures | `references/core-api.md` |

## Set up the instance

Create it **once**, in its own module, and export it. Two modules that each call `Analytics()` produce two independent instances with two independent plugin sets, and the second one's events go nowhere.

```js
// src/analytics.js
import Analytics from 'analytics'
import googleAnalytics from '@analytics/google-analytics'

const analytics = Analytics({
  app: 'my-app-name',
  plugins: [
    googleAnalytics({ measurementIds: ['G-abc123'] })
  ]
})

export default analytics
```

`app`, `version`, `debug`, and `plugins` are the only config keys.

Provider plugins are **factories — invoke them**. `plugins: [googleAnalytics]` (uninvoked) is not a plugin, and it fails without a useful error. A hand-written local plugin, by contrast, is a plain object and goes in as-is. This asymmetry is the single most common setup mistake.

Set `debug: process.env.NODE_ENV === 'development'` to connect Redux DevTools and watch every event flow through the lifecycle. It's the fastest way to see what's actually happening.

## Track an event

```js
import analytics from './analytics'

analytics.page()                                        // page view
analytics.track('itemPurchased', { price: 11, sku: '1234' })
analytics.identify('user-123', { name: 'steve', plan: 'pro' })
analytics.reset()                                       // on logout
```

Every call fans out to **every** plugin that implements that method. To scope a single call, pass the `options` argument:

```js
// everywhere except segment
analytics.track('cartAbandoned', { items: ['xyz'] }, {
  plugins: { segment: false }
})

// nowhere except customerio
analytics.track('internalEvent', {}, {
  plugins: { all: false, customerio: true }
})
```

The keys are plugin **names**, not package names, and `all` is the wildcard. For `page()`, options is still the second argument — so pass an empty object first: `analytics.page({}, { plugins: {...} })`. Skipping that empty object means your selector is silently parsed as page data.

Events fired **before plugins are enabled are dropped, not queued**. If plugins start disabled (consent gating), do the work inside `.then()`.

## Consent gating

Two mechanisms, and the difference matters.

**`enabled: false` — the strong one.** The plugin's `initialize` never runs, so the vendor's script is never injected. Nothing loads until you say so.

```js
const analytics = Analytics({
  app: 'my-app',
  plugins: [
    googleAnalytics({ measurementIds: ['G-abc123'], enabled: false })
  ]
})

// user accepted the cookie banner
analytics.plugins.enable('google-analytics').then(() => {
  analytics.page()   // fire it here — calls made before this were dropped
})
```

**`abort` — the weaker one.** The script has already loaded; you're just cancelling calls. Fine for do-not-track, insufficient if the requirement is "no third-party code before consent."

```js
const consentGate = {
  name: 'consent-gate',
  trackStart: ({ abort }) => {
    if (!hasConsent()) return abort('no consent')   // MUST return it
  }
}
```

`return abort(...)` — calling `abort()` bare does nothing and looks exactly like working code. Abort is available on `*Start` hooks only.

For browser do-not-track, `analytics-plugin-do-not-track` already does this; see `references/provider-plugins.md`.

## The three things that break implementations

Worth knowing before you touch the code, because none of them error.

1. **Plugin array order is a pipeline.** Validators and enrichers must be listed **before** the provider plugins they gate or modify. Register an enricher after Google Analytics and it enriches nothing.

2. **A plugin that loads a script needs `loaded()`.** It returns a boolean telling analytics when the vendor global actually exists; until then calls are held. Omit it and the session's first events fire into a `<script>` tag that hasn't finished loading. They vanish — for fast clickers and cold caches only, which is why QA never catches it.

3. **Namespaced hooks must return the payload.** `'track:hubspot': ({ payload }) => {...}` shapes what HubSpot alone receives — but only if you `return` the new payload. Mutating without returning is a no-op.

Detail on all three, plus the full 33-event lifecycle, is in `references/lifecycle-and-hooks.md` and `references/writing-plugins.md`.

## Verify before you call it done

Nothing here throws, so "the code looks right" is not evidence. Two checks:

1. **Run the linter** — `python scripts/check_analytics.py <paths>`. It flags uninvoked plugin factories, plugins missing `name`, script-loading plugins with no `loaded()`, `abort()` called but not returned, enrichers ordered after their provider, `page(options)` missing the empty first argument, and GA4 configured with `trackingId` instead of `measurementIds`. It's static analysis — it cannot tell you an event actually fired.

2. **Watch an event land.** Turn on `debug: true` and confirm the event moves through the lifecycle in Redux DevTools, then confirm it arrives in the destination's own dashboard. If you can't do that, say plainly that the implementation is unverified rather than declaring it done.

## Reference files

- `references/core-api.md` — every method signature: `track`/`page`/`identify`/`user`/`reset`/`ready`/`on`/`once`/`getState`/`storage.*`/`plugins.*`, and the `options.plugins` selector.
- `references/lifecycle-and-hooks.md` — all 33 lifecycle events, the Start/core/End/Aborted convention, the hook argument object, aborting, namespaced `event:plugin` hooks, enrichment and validation patterns.
- `references/writing-plugins.md` — the plugin object, `loaded()`, custom `methods` (and the arrow-function `this.instance` trap), extending or cloning third-party plugins with `Object.assign`.
- `references/provider-plugins.md` — config keys for GA4, GTM, Segment, Mixpanel, do-not-track, event-validation, original-source, and the wider catalog.
- `references/frameworks-and-spa.md` — SPA page views (React Router, `onRouteChange`, Gatsby), `use-analytics`, UTM/campaign data, TypeScript event maps, and the CDN ad-blocker trap.
- `references/utils.md` — the `@analytics/*` util packages: storage, cookies, forms, url, router, listeners, activity, scroll, queue, redaction, types.

## Credits & source of truth

`analytics` is by [David Wells](https://github.com/DavidWells) and contributors — [DavidWells/analytics](https://github.com/DavidWells/analytics) (MIT). Official docs: **[getanalytics.io](https://getanalytics.io)**.

This skill distills those docs; it is unofficial. The library moves, so when reality disagrees with this skill, reality wins — check [getanalytics.io](https://getanalytics.io) and the [plugin catalog](https://getanalytics.io/plugins/) for the current API before assuming a signature here is still right.

One place they already disagree: several pages on getanalytics.io still show `trackingId` (Universal Analytics) against `@analytics/google-analytics`, which is now GA4 and requires `measurementIds`. Follow the library.
