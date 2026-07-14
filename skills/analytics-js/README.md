# analytics-js

> Vendor-agnostic analytics that actually delivers events — correct plugin wiring, correct lifecycle hooks, verified. Because nothing in analytics-js throws, and a plugin that drops every event looks exactly like one that works.

```bash
npx skills add ketanip/agent-skills --skill analytics-js
```

> Part of the [ketanip/agent-skills](https://github.com/ketanip/agent-skills) collection — drop `--skill analytics-js` to install every skill in it. Works with Claude Code, Cursor, Copilot, Windsurf, Cline — any agent that supports [skills.sh](https://skills.sh).

---

## The setup that looks right and sends nothing

```js
const analytics = Analytics({
  app: 'my-app',
  plugins: [
    googleAnalytics({ trackingId: 'UA-123' }),   // GA4 wants measurementIds
    segmentPlugin,                                // factory, never invoked
    enrichGA,                                     // registered after the plugin it enriches
    consentGate                                   // gate registered after the providers it gates
  ]
})
```

No error. No warning. Nothing red in the console. The instance builds, the app runs, the PR looks clean.

Google Analytics receives nothing at all. Segment isn't registered — a function is. The enricher enriches an empty set. The consent gate guards providers that already ran.

Four separate silent failures, in six lines, in the shape people actually write.

**Three of those four appear in analytics-js's own documentation**, which is the honest reason this skill exists: an agent copying from the docs reproduces them faithfully.

---

## What the skill does about it

It treats **the plugins array as a pipeline** — order is semantics, not style — and ships a linter so the check is mechanical rather than a matter of anyone's attention.

```bash
python skills/analytics-js/scripts/check_analytics.py src/
```

```
ERROR src/analytics.js:5: @analytics/google-analytics (GA4) takes `measurementIds: ['G-...']`,
                          not `trackingId`. A GA4 plugin with no measurement ID silently sends nothing.
ERROR src/analytics.js:6: `segmentPlugin` is a plugin factory from '@analytics/segment' but is
                          registered uninvoked -- it is a function, not a plugin object, so it is
                          silently ignored. Call it: segmentPlugin({ ... }).
ERROR src/analytics.js:7: Plugin 'enrich-ga' hooks 'track:google-analytics' but is registered AFTER
                          'google-analytics' in the plugins array. An enricher listed after its
                          provider enriches nothing. Move it before.
ERROR src/analytics.js:8: Validation/consent plugin 'consent-gate' can abort calls but is registered
                          after provider plugin(s) (google-analytics, segment). Gates must come first.
ERROR src/vendor.js:12:   Plugin 'vendor' loads a third-party script in initialize() but has no
                          `loaded()`. The session's first events fire into a script tag that hasn't
                          finished loading. They vanish silently.
ERROR src/track.js:31:    abort() is called but not returned -- the call is NOT cancelled.
```

Zero dependencies, Python 3 only, exit code `1` on errors — drops straight into a pre-commit hook or CI step. Useful on its own even if you never install the skill.

It was validated against **145 code samples from the official documentation**. The only errors it reports there are real ones.

---

## The traps, and why they survive review

**`loaded()` is optional, and omitting it loses events.** It returns a boolean telling analytics when the vendor's global actually exists. Until it's true, calls are queued. Leave it out and the session's first events fire into a `<script>` tag that's still downloading — so they're lost for fast clickers and cold caches, and for nobody in QA.

**The plugins array is a pipeline.** Enrichers and validators run in array order. Put your consent gate after Google Analytics and it gates nothing, having already let the call through.

**`abort()` must be *returned*.** `abort('no consent')` on its own is a no-op that reads exactly like a working guard.

**Namespaced hooks must return the payload.** `'track:hubspot'` shapes what HubSpot alone receives — but only if you return the new object. Mutate without returning and your enrichment silently evaporates.

**`analytics.page({ plugins: {...} })` is not a plugin selector.** The first argument is page *data*. Your routing config gets recorded as page properties and the event goes everywhere.

**GA4 double-counts SPA page views** — it auto-fires on history changes, so your route-change `page()` call becomes the second one. The fix is in the GA4 admin, not your code, and no amount of debugging the JS will find it.

---

## What your agent learns

| Reference | What it covers |
|---|---|
| **SKILL.md** | Decision table → set up → track → consent → verify. Routes to a reference only when the task needs one. |
| **core-api.md** | Every signature: `track`/`page`/`identify`/`user`/`reset`/`ready`/`on`/`once`/`getState`/`storage.*`/`plugins.*`, and the `options.plugins` selector |
| **lifecycle-and-hooks.md** | All 33 lifecycle events, the Start/core/End/Aborted convention, aborting, namespaced `event:plugin` hooks, enrichment and validation |
| **writing-plugins.md** | The plugin object, `loaded()`, custom `methods` (and the arrow-function `this.instance` trap), extending providers via `Object.assign` |
| **provider-plugins.md** | Config keys for GA4, GTM, Segment, Mixpanel, do-not-track, event-validation, original-source |
| **frameworks-and-spa.md** | SPA page views (React Router, `onRouteChange`, Gatsby), `use-analytics`, UTM/campaign data, TypeScript event maps, the CDN ad-blocker trap |
| **utils.md** | The `@analytics/*` packages: storage, cookies, forms, url, router, listeners, activity, scroll, queue, redaction, types |

Loaded on demand. Asking for a track call doesn't drag the cross-domain storage spec into your context.

---

## Just talk to your agent normally

**"Add analytics to our Next.js app with GA4 and Segment"**
→ One exported instance, plugins invoked as factories, `measurementIds` not `trackingId`, and page views wired through `onRouteChange` — plus a note to disable GA4's enhanced measurement so it doesn't double-count.

**"Send this event to Customer.io but not Google Analytics"**
→ `options.plugins`, keyed by plugin name, with the `all: false` whitelist form — instead of a hand-rolled `if` at the call site.

**"Our analytics needs to respect the cookie banner"**
→ `enabled: false` so the vendor script never loads before consent, then `plugins.enable().then()` — and it knows that events fired before that point are dropped, not queued.

**"Add app version to everything we send to HubSpot only"**
→ A `'track:hubspot'` namespaced hook that *returns* the enriched payload, registered before the HubSpot plugin.

**"Events aren't showing up"**
→ Runs the linter, then walks the ladder: is the plugin registered, did it load, is a gate aborting, is the enricher ordered wrong.

---

## Honest limits

- The linter is **static analysis over source text**. It cannot tell you whether an event actually fired in a browser. Turn on `debug: true`, watch it move through the lifecycle in Redux DevTools, and confirm it lands in the destination's dashboard — the skill says so too, rather than letting your agent declare victory.
- Package shapes drift. The linter knows which packages are factories from a maintained list; a brand-new community plugin it hasn't heard of is left alone rather than guessed at.
- Where the upstream docs have gone stale (the GA4 `trackingId` examples), this skill follows the library, not the docs.

---

## Credits

`analytics` is created and maintained by **[David Wells](https://github.com/DavidWells)** and its contributors.

- **Library** — [DavidWells/analytics](https://github.com/DavidWells/analytics) (MIT)
- **Documentation** — [getanalytics.io](https://getanalytics.io)

This skill is an independent, unofficial distillation of that public documentation into a form an AI coding agent loads on demand. All credit for the library and its docs belongs to its authors; any errors in this skill are mine, not theirs. Not affiliated with or endorsed by the `analytics` maintainers.

If this skill is useful to you, the library deserves the star: **⭐ [github.com/DavidWells/analytics](https://github.com/DavidWells/analytics)**

---

## Skill details

| | |
|---|---|
| **Skill name** | `analytics-js` |
| **Collection** | [ketanip/agent-skills](https://github.com/ketanip/agent-skills) |
| **Activation** | Automatic on analytics-js, getanalytics.io, `@analytics/*`, `use-analytics`, and general "add analytics / track events" work |
| **Reference files** | 6 focused files, loaded on demand |
| **Bundled tooling** | `check_analytics.py` linter (zero dependencies, CI-ready) |
| **Author** | [Ketan Iralepatil](https://github.com/ketanip) |
