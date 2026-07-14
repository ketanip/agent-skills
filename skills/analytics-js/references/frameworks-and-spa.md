# SPAs, React, and campaign data

## The SPA page-view problem

`analytics.page()` fires once, on hard load. In a single-page app every subsequent navigation is a `pushState` — no page load, no page view. Unless you wire route changes yourself, your analytics shows one page view per *session* and a bounce rate that looks like a catastrophe.

Two ways to fix it. Pick by whether you want router coupling.

### Framework-agnostic: `@analytics/router-utils`

Listens for `pushState` directly. Works with any router, or none.

```js
import onRouteChange from '@analytics/router-utils'   // default export
import analytics from './analytics'

analytics.page()                                // initial load
onRouteChange((newRoutePath) => analytics.page())  // every route change
```

This is the answer for Next.js, Vue, Svelte, or a hand-rolled router.

### React Router: `useLocation` + `useEffect`

```js
// index.js — Provider must wrap the Router, Router must wrap App
import { BrowserRouter } from 'react-router-dom'
import { AnalyticsProvider } from 'use-analytics'
import analytics from './analytics'

ReactDOM.render(
  <AnalyticsProvider instance={analytics}>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </AnalyticsProvider>,
  document.getElementById('root')
)
```

```js
// App.js — the core pattern
import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useAnalytics } from 'use-analytics'

export default function App() {
  const location = useLocation()
  const { page } = useAnalytics()

  useEffect(() => {
    page()
  }, [location])

  return <Routes>{/* ... */}</Routes>
}
```

`App` has to be *inside* `BrowserRouter` for `useLocation()` to resolve — hence the Provider → Router → App nesting.

Under React 18 `StrictMode` in development, effects run twice, so you'll see doubled page views locally. That's dev-only; don't "fix" it by removing the dependency array.

### Gatsby

`gatsby-plugin-analytics` handles page tracking automatically. Add `{ resolve: 'gatsby-plugin-analytics' }` to `gatsby-config.js`.

### Then go turn off GA4's version of this

GA4 *also* auto-fires page views on history changes. Wire up route tracking without disabling that and every SPA navigation is counted twice. Fix it in the GA4 admin — Data Streams → Enhanced measurement → uncheck **"Page changes based on browser history events."** There is no code-side fix.

## `use-analytics` (React) — optional

React works fine by importing the instance directly. `use-analytics` exists if you'd rather inject it via context.

```bash
npm install analytics use-analytics
```

```js
import { AnalyticsProvider, useAnalytics, withAnalytics, AnalyticsContext } from 'use-analytics'

// hooks
const { track, page, identify } = useAnalytics()

// class components
class Thing extends React.Component {
  static contextType = AnalyticsContext
  render() { const { track } = this.context }
}

// HOC → this.props.analytics
export default withAnalytics(App)
```

Both styles can coexist. In a component that isn't under the Provider, the plain `import analytics from './analytics'` still works.

## Campaign / UTM parameters

Analytics emits a **`campaign`** lifecycle event whenever the URL contains UTM parameters. The Google Analytics plugin forwards them on its own; hook `campaign` when you want the data in *other* tools or your own storage.

**The keys are renamed, and `utm_campaign` is the one that bites:**

| URL param | `payload.campaign` key |
|---|---|
| `utm_source` | `source` |
| `utm_medium` | `medium` |
| `utm_term` | `term` |
| `utm_content` | `content` |
| `utm_campaign` | **`name`** |

```js
// as a plugin
const saveCampaign = {
  name: 'save-campaign-data',
  campaign: ({ payload }) => {
    // { source, medium, term, content, name }
    persist(payload.campaign)
  }
}

// or as a listener
analytics.on('campaign', ({ payload }) => {
  console.log('utm data', payload.campaign)
})
```

Reaching for `payload.campaign.campaign` is the mistake. It's `payload.campaign.name`.

To capture attribution and then scrub the address bar:

```js
import { getSearch, removeSearch } from '@analytics/url-utils'

const { utm_source } = getSearch()
removeSearch(/^utm_/)   // with no url argument this rewrites history in place
```

For first-touch attribution that survives later visits, `analytics-plugin-original-source` already does this — see `provider-plugins.md`.

## Persisting page views

A custom plugin on the `page` hook. `payload.properties` carries `path`, `title`, `url`.

```js
const pagesViewedKey = 'PAGES_VIEWED'
const getViews = () => JSON.parse(localStorage.getItem(pagesViewedKey) || '[]')
const setViews = (data) => localStorage.setItem(pagesViewedKey, JSON.stringify(data))

const persistPageViews = {
  name: 'persist-page-views',
  page: ({ payload }) => {
    setViews(getViews().concat(payload.properties.path))
  }
}
```

## Type-safe events (TypeScript)

Nothing stops `analytics.track('purchse', { revenu: 10 })` from compiling. The event map pattern gives you autocomplete and a compile error on typos:

```ts
type EventMap = {
  'user:signed_up':    { plan: 'free' | 'pro'; referrer?: string }
  'cart:item_added':   { sku: string; price: number; quantity: number }
  'checkout:completed':{ orderId: string; revenue: number; currency: string }
}

function track<K extends keyof EventMap>(event: K, properties: EventMap[K]) {
  return analytics.track(event, properties)
}

track('cart:item_added', { sku: 'A1', price: 9.99, quantity: 1 })  // ✅
track('cart:item_add',   { sku: 'A1' })                            // ✗ bad name AND missing fields
```

Compile-time types only bind code you control. For runtime enforcement — bad data from a third party, a CMS, or a hand-written snippet — you still want a validation plugin on `trackStart`. See `lifecycle-and-hooks.md`.

## Loading via CDN: the ad-blocker trap

The UMD build exposes a global `_analytics`, and you must call `.init()`:

```html
<script src="https://unpkg.com/analytics/dist/analytics.min.js"></script>
<script>
  const analytics = _analytics.init({ app: 'my-app', plugins: [] })
</script>
```

But uBlock Origin and friends block **any URL containing the word "analytics"** — so that unpkg URL is blocked outright for a meaningful share of visitors, and it fails silently for exactly the audience most likely to be technical.

If you must use a script tag, self-host the bundle under a neutral filename:

```html
<script src="https://cdn.my-site.com/load-this.min.js"></script>
```

Bundling from npm sidesteps this entirely, which is one more reason to prefer it.
