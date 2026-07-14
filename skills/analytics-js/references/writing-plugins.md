# Writing & extending plugins

A plugin is a plain JavaScript object. That is the whole idea — which is why extending someone else's plugin is just `Object.assign`.

## The plugin object

```
name       string    REQUIRED — the plugin's namespace
config     object    resolved configuration
EVENTS     object    events the plugin exposes
initialize function  load the third-party script
page       function  page-view tracking method
track      function  event tracking method
identify   function  user identify method
loaded     function  returns a boolean: is the vendor script ready?
ready      function  fires when the plugin is ready
methods    object    custom methods mounted at analytics.plugins.<name>.*
```

`name` is required. **Everything else is optional** — if you don't hook page tracking, omit `page`. Any lifecycle event name is also a valid key (`trackStart`, `pageEnd`, `'track:segment'`, …).

Convention: export a **factory** that takes user config and returns the object. That's why provider plugins are invoked in the `plugins` array (`googleAnalytics({...})`) while a one-off local plugin can be a bare object.

## A provider plugin (wraps a third-party script)

```js
export default function providerPluginExample(userConfig) {
  return {
    name: 'my-example-plugin',
    config: {
      whatEver: userConfig.whatEver,
      elseYouNeed: userConfig.elseYouNeed
    },
    initialize: ({ config }) => {
      // load the vendor script onto the page
    },
    page: ({ payload }) => {
      // call the vendor's page tracking
    },
    track: ({ payload }) => {
      // call the vendor's event tracking
    },
    identify: ({ payload }) => {
      // call the vendor's identify
    },
    loaded: () => {
      // boolean: is it safe to send data to the vendor yet?
      return !!window.myPluginLoaded
    }
  }
}
```

### `loaded()` is the part people skip, and it's the part that matters

`loaded()` tells analytics-js **when the vendor's global actually exists**. The `ready` event waits for `initialize` to have run *and* `loaded()` to return true, and until then calls are held rather than fired.

Omit it and you get the bug where the first few events of a session vanish: the visitor lands, your code calls `analytics.track()`, and the plugin forwards it to `window.vendor` — which is still an in-flight `<script>` tag. Nothing throws. The events are simply gone, and only for fast clickers and cold caches, which is why it survives QA.

If your plugin loads a script, it needs a `loaded()`.

## A custom plugin (reacts to events)

No vendor, no script — just logic on the lifecycle. This is also the minimal dev logger:

```js
const loggerPlugin = {
  name: 'logger',
  page:     ({ payload }) => { console.log('page', payload) },
  track:    ({ payload }) => { console.log('track', payload) },
  identify: ({ payload }) => { console.log('identify', payload) }
}
```

Hook any event, including namespaced ones:

```js
export default function myPlugin(userConfig) {
  return {
    name: 'my-plugin',
    bootstrap:  ({ payload, config, instance }) => {},
    pageStart:  ({ payload, config, instance }) => {},
    trackStart: ({ payload, config, instance }) => {},
    'track:customerio': ({ payload, config, instance }) => {
      // shape the data sent to customer.io specifically — return the payload
    },
    trackEnd:   ({ payload, config, instance }) => {}
  }
}
```

## Custom methods on the instance

Anything under `methods` is mounted at `analytics.plugins.<name>.<method>()`. This is how a plugin exposes vendor features the core API doesn't have — Segment's `group()` is exactly this.

```js
const pluginOne = {
  name: 'one',
  methods: {
    myCustomThing(one, two, three) {
      const analyticsInstance = this.instance     // shorthand method → `this` works
      console.log('Use full analytics instance', analyticsInstance)
    },
    otherCustomThing: (one, two, ...args) => {
      // Arrow functions break `this.instance`.
      // The instance is injected as the LAST argument instead.
      const analyticsInstance = args[args.length - 1]
    },
    async fireCustomThing(one, two) {
      const { track } = this.instance
      track('customThing')
      return 'data'
    }
  }
}
```

```js
analytics.plugins.one.myCustomThing()
```

**The arrow-function trap is documented and real:** an arrow method has no `this`, so `this.instance` is undefined. Either write a shorthand method, or pull the instance off the end of `args`. Don't half-do it — `this.instance.track()` inside an arrow throws at runtime, in a code path (a custom method) that often has no test.

## Extending a third-party plugin

Plugins are objects, so override by merging. To swap out GA's `track` while keeping everything else:

```js
import googleAnalytics from '@analytics/google-analytics'

const originalGoogleAnalytics = googleAnalytics({ measurementIds: ['G-abc123'] })

function myCustomTrack({ payload }) {
  // send to a custom backend instead
}

const customGoogleAnalytics = Object.assign({}, originalGoogleAnalytics, {
  track: myCustomTrack
})

const analytics = Analytics({
  app: 'my-app-name',
  plugins: [ customGoogleAnalytics ]
})
```

The same trick runs **two instances of one provider** — override `name`, because two plugins with the same name collide:

```js
const GTMOne = googleTagManager({ containerId: 'GTM-123xyz' })
const GTMTwo = Object.assign({}, googleTagManager({ containerId: 'GTM-456abc' }), {
  name: 'google-tag-manager-two'
})
```

Often you don't need to override at all — a *separate* plugin with a `'track:google-analytics'` hook can shape GA's payload without touching GA's plugin. Prefer that when you only want to change data, not behavior.

## Plugin array order

Enrichers and validators must come **before** the provider plugins they modify or gate. The array is the pipeline.

```js
plugins: [
  eventValidation({ context: 'app', objects: ['user', 'sites'] }),  // gate first
  enrichWithAppVersion,                                             // then enrich
  googleAnalytics({ measurementIds: ['G-abc123'] }),                // then send
  segmentPlugin({ writeKey: '123-xyz' })
]
```

## Naming

- Community plugins published to npm: `analytics-plugin-{name}` (e.g. `analytics-plugin-do-not-track`).
- Official/first-party plugins are scoped: `@analytics/{provider}`.

The `name` field inside the plugin is the **namespace** — it's what `options.plugins`, `plugins.enable/disable`, and `event:name` hooks all key off. It is not the package name.
