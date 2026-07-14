# Lifecycle & hooks

Everything in analytics-js is driven by lifecycle events. A plugin is just an object whose keys are event names; a listener is `analytics.on(eventName, fn)`. Same event names for both.

## The Start / core / End / Aborted convention

For each core action `X` — `page`, `track`, `identify`, `initialize`, `setItem`, `removeItem`, `reset`:

| Hook | When it runs | What it's for |
|---|---|---|
| `XStart` | before the action | The **only** place a call can be cancelled or its payload rewritten. `abort` is available here. |
| `X` | the action itself | What **provider plugins implement** — "if your plugin tracks page views, this is the event to fire on". |
| `XEnd` | after every plugin's `X` has run | Post-hoc logic, callbacks. |
| `XAborted` | instead of completion, when a plugin cancelled it | Cleanup, logging, dev warnings. |

Getting this wrong is the most common structural mistake: enrichment and validation belong in `XStart` (where you can still change or stop the call), not in `X` (where the provider has already been handed the payload).

## The full event list

**Initialization** — `bootstrap`, `params`, `campaign`, `initializeStart`, `initialize`, `initializeEnd`, `ready`

- `bootstrap` — first event fired. **Plugins only; `.on()`/`.once()` listeners are not allowed on it**, because the instance doesn't exist yet.
- `params` — analytics parsed URL parameters.
- `campaign` — those params contained UTM parameters.
- `initializeStart` — lets a plugin cancel the loading of **other** plugins. This is the consent / do-not-track kill switch.
- `ready` — all providers fully loaded. Waits for both `initialize` and `loaded()` to return true.

**Page** — `pageStart`, `page`, `pageEnd`, `pageAborted`
**Track** — `trackStart`, `track`, `trackEnd`, `trackAborted`
**Identify** — `identifyStart`, `identify`, `identifyEnd`, `identifyAborted`, `userIdChanged`
**Storage** — `setItemStart`, `setItem`, `setItemEnd`, `setItemAborted`, `removeItemStart`, `removeItem`, `removeItemEnd`, `removeItemAborted`
**Network** — `online`, `offline` — `online` fires only when *returning* from an offline state, never on a normal load.
**Other** — `resetStart`, `reset`, `resetEnd`, `registerPlugins`, `enablePlugin`, `disablePlugin`

The authoritative list lives in [`analytics-core/src/events.js`](https://github.com/DavidWells/analytics/blob/master/packages/analytics-core/src/events.js).

## The hook argument

Every hook receives a **single object**, destructured:

```js
{
  payload,    // the event payload — for track: payload.event, payload.properties
  config,     // this plugin's own resolved config
  instance,   // the full analytics instance
  abort       // cancellation fn — only on *Start hooks
}
```

## Aborting a call

`abort(reason)` is available on the `*Start` hooks. **You must `return` it** — calling it bare does nothing, which is a silent failure that looks exactly like working code.

```js
const consentPlugin = {
  name: 'consent-gate',
  trackStart: ({ payload, abort }) => {
    if (!hasConsent()) {
      return abort('No consent — cancelling track call')   // ← return, not just call
    }
  }
}
```

Abort in `initializeStart` cancels **plugin loading across the board**, not just for the aborting plugin — that's the point of it, and why do-not-track works.

Abort is broad: it cancels the call, not one destination. To suppress a *single* destination, use `options.plugins` at the call site, or noOp inside a namespaced hook. See `core-api.md`.

An aborted call fires the matching `*Aborted` event, which is where a dev-mode warning belongs.

## Namespaced hooks: `event:plugin-name`

The suffix is the target plugin's `name`. The hook runs **immediately before that one plugin handles the event**, and **its return value becomes the payload for that plugin only**.

This is the mechanism for per-destination payload shaping — different providers want different field names for the same event, and this is how you give it to them without polluting the others.

```js
const enrichHubspot = {
  name: 'enrich-hubspot',
  'track:hubspot': ({ payload }) => {
    const properties = Object.assign({}, payload.properties, {
      dataJustForHubspot: 'hubspot only data'
    })
    // MUST return the updated payload — returning nothing discards your changes
    return Object.assign({}, payload, { properties })
  }
}
```

Two things to internalize:

1. **Return the payload or lose it.** A namespaced hook that mutates and returns nothing is a no-op.
2. **Order in the `plugins` array matters.** Enrichers and validators must be listed **before** the provider plugins they modify or gate.

## Listeners

Same events, subscribed from outside a plugin. `on` and `once` both return an unsubscribe function.

```js
const removeListener = analytics.on('identify', ({ payload }) => {
  // custom business logic
})

removeListener()
```

Use a listener for app-level reactions (redirect after identify, toast on error). Use a plugin when the logic is reusable, needs to alter the payload, or needs to abort — listeners cannot abort.

## Global enrichment vs per-destination enrichment

```js
const enrichAll = {
  name: 'enrich-all',
  // runs before EVERY provider — payload changes flow to all of them
  trackStart: ({ payload }) => {
    return Object.assign({}, payload, {
      properties: Object.assign({}, payload.properties, {
        appVersion: '1.2.3'
      })
    })
  }
}
```

`trackStart` → everyone sees it. `'track:mixpanel'` → only Mixpanel sees it. Pick deliberately; sending a provider fields it doesn't understand is usually harmless, but sending PII to one that shouldn't have it is not.

## Validation as a plugin

Cancel malformed events at the boundary instead of letting each provider handle them differently:

```js
const validation = {
  name: 'event-validation',
  trackStart: ({ payload, abort }) => {
    if (!/^[a-z]+:[a-z]+_[a-z]+$/.test(payload.event)) {
      return abort(`Event "${payload.event}" does not meet the naming convention`)
    }
  }
}
```

In development, **throwing** instead of aborting is a legitimate choice — it makes the mistake loud at the point of the bad call rather than silently dropping it:

```js
trackStart: ({ payload }) => {
  if (!isValid(payload)) {
    throw new Error('Bad analytics payload. Fix the caller.')
  }
}
```

There's a ready-made version of this: `analytics-plugin-event-validation`, which enforces `context:object_action` names (`app:user_signup`). See `provider-plugins.md`.
