# Core API

Every method on the instance returned by `Analytics({...})`.

Source: the [analytics API docs](https://getanalytics.io/api/) — library by [David Wells](https://github.com/DavidWells/analytics), MIT.

## Contents

- [Install & initialize](#install--initialize)
- [track](#analyticstrackeventname-payload-options-callback)
- [page](#analyticspagedata-options-callback)
- [identify](#analyticsidentifyuserid-traits-options-callback)
- [The `options.plugins` selector](#the-optionsplugins-selector)
- [user](#analyticsuserkey)
- [reset](#analyticsresetcallback)
- [ready](#analyticsreadycallback)
- [on / once](#analyticsonname-callback--analyticsoncename-callback)
- [getState](#analyticsgetstatekey)
- [storage](#analyticsstorage)
- [plugins.enable / plugins.disable](#analyticspluginsenable--analyticspluginsdisable)

## Install & initialize

```bash
npm install analytics
```

```js
import Analytics from 'analytics'
import googleAnalytics from '@analytics/google-analytics'

const analytics = Analytics({
  app: 'my-app-name',      // string  — name of site / app
  version: 100,            // string|number — version of your app
  debug: false,            // boolean — connects Redux DevTools
  plugins: [               // Array<AnalyticsPlugin>
    googleAnalytics({ measurementIds: ['G-abc123'] })
  ]
})

export default analytics
```

`app`, `version`, `debug`, `plugins` are the **only** documented config keys.

Create the instance once in its own module and export it. Importing `analytics` from two places that each call `Analytics()` gives you two independent instances with two independent plugin sets, and the second one's events go nowhere useful.

CDN build: `<script src="https://unpkg.com/analytics/dist/analytics.min.js"></script>`.

CommonJS needs `.default` on both the core and the plugins:

```js
const analyticsLib = require('analytics').default
const segmentPlugin = require('@analytics/segment').default
```

## `analytics.track(eventName, [payload], [options], [callback])`

Triggers the `track` hook in every installed plugin.

```js
analytics.track('buttonClicked')

analytics.track('itemPurchased', {
  price: 11,
  sku: '1234'
})

// callback can be the 2nd, 3rd, or 4th argument — arguments are type-sniffed
analytics.track('newsletterSubscribed', () => {
  console.log('do this after track')
})
```

Inside plugin hooks the payload arrives as `payload.event` (the name) and `payload.properties` (the object).

## `analytics.page([data], [options], [callback])`

Triggers the `page` hook in every installed plugin. Records a page view.

```js
analytics.page()

analytics.page({ url: 'https://google.com' })   // override page data

analytics.page(() => { /* after page call */ })  // callback as 1st arg
```

## `analytics.identify(userId, [traits], [options], [callback])`

Triggers `identify` in every plugin **and persists user data to localStorage**, so `analytics.user()` keeps working across page loads.

```js
analytics.identify('xyz-123')

analytics.identify('xyz-123', {
  name: 'steve',
  company: 'hello-clicky'
})
```

## The `options.plugins` selector

`track`, `page`, and `identify` all take the same third argument. It controls **which destinations this one call goes to** — it does not enable or disable the plugin itself.

```js
// everywhere except segment
analytics.track('cartAbandoned', { items: ['xyz'] }, {
  plugins: { segment: false }
})

// nowhere except customerio
analytics.track('customerIoOnlyEvent', { price: 11 }, {
  plugins: {
    all: false,        // opt out of everything...
    customerio: true   // ...then whitelist
  }
})
```

`all` is the reserved wildcard. The other keys are plugin **`name`s** (the plugin's own namespace — `segment`, `google-analytics`), never npm package names.

For `page()`, options is still the *second* positional argument, so you must pass an explicit empty object first. `analytics.page({ plugins: {...} })` silently reads your selector as page data:

```js
analytics.page({}, { plugins: { all: false, 'google-analytics': true } })
```

## `analytics.user([key])`

Synchronous. Returns user data; `key` is a `dot.prop` path.

```js
const userData    = analytics.user()
const userId      = analytics.user('userId')
const companyName = analytics.user('traits.company.name')
```

## `analytics.reset([callback])`

Clears the visitor's id and traits from storage and resets analytic state. Fires `resetStart` → `reset` → `resetEnd`. Call it on logout.

```js
analytics.reset(() => {
  console.log('user data cleared')
})
```

## `analytics.ready(callback)`

Fires once all providers are "loaded **or were skipped**" — a plugin that was disabled or aborted does not hang `ready` forever.

```js
analytics.ready(({ plugins }) => {
  // every plugin's initialize has run and its loaded() returned true
})
```

## `analytics.on(name, callback)` / `analytics.once(name, callback)`

Attach a handler to any lifecycle event. **Both return an unsubscribe function** — call it to detach.

```js
const removeListener = analytics.on('track', ({ payload }) => {
  console.log('track fired', payload)
})

removeListener()   // detach
```

`once` fires at most one time. `bootstrap` is the one event you cannot subscribe to this way — it fires before the instance exists, so it is plugin-only.

In React, an `on()` call inside a component without the matching unsubscribe in the effect's cleanup leaks a listener on every remount, and the handler then fires N times per event.

## `analytics.getState([key])`

Returns a **snapshot** of the internal Redux store. It does not mutate in place — re-call it, or use a listener, rather than holding a reference.

```js
analytics.getState()
analytics.getState('context.offline')
```

## `analytics.storage`

Cross-mechanism persistence (localStorage → cookies → window, degrading as availability allows).

```js
const { storage } = analytics

storage.setItem('storage_key', 'value')
storage.getItem('storage_key')
storage.removeItem('storage_key')
```

These calls run through the lifecycle too (`setItemStart` / `setItem` / `setItemEnd` / `setItemAborted`, and the `removeItem*` equivalents), so a plugin can intercept a key/value and rewrite or abort it before it is persisted. That is how the redaction pattern works.

## `analytics.plugins.enable` / `analytics.plugins.disable`

Both accept a plugin `name` or an array of names, and **return a promise**. This is the real enable/disable — as opposed to `options.plugins`, which only suppresses a single call.

```js
analytics.plugins.enable('google-analytics').then(() => { /* loaded */ })
analytics.plugins.enable(['google-analytics', 'segment']).then(() => {})
analytics.plugins.disable(['google-analytics', 'segment']).then(() => {})
```

Firing these emits the `enablePlugin` / `disablePlugin` lifecycle events.

`analytics.plugins` is also where a plugin's custom `methods` are mounted — see `writing-plugins.md`.

Note that `track`/`page`/`identify` document a trailing **callback**, not a promise. Reach for the callback (or a `.on('trackEnd')` listener) when you need to sequence work after a call.
