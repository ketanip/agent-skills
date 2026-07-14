# Util packages

Standalone, tree-shakable helpers from the analytics ecosystem. They work with or without the `analytics` core — most are a few hundred bytes. Reach for these instead of hand-rolling; the edge cases (storage unavailable, existing `window.onerror`, throttling) are already handled.

## Contents

| Package | Use it when |
|---|---|
| [`@analytics/storage-utils`](#analyticsstorage-utils) | persist a value, degrading across localStorage → cookie → session → window |
| [`@analytics/localstorage-utils`](#single-mechanism-storage) | localStorage only, with a safe fallback |
| [`@analytics/session-storage-utils`](#single-mechanism-storage) | value should die with the tab |
| [`@analytics/global-storage-utils`](#single-mechanism-storage) | in-memory store / isomorphic global |
| [`@analytics/cookie-utils`](#analyticscookie-utils) | you specifically need a cookie (server-readable, cross-subdomain) |
| [`@analytics/remote-storage-utils`](#analyticsremote-storage-utils) | share IDs across domains you own |
| [`@analytics/form-utils`](#analyticsform-utils) | track form submits/changes while redacting sensitive fields |
| [`@analytics/url-utils`](#analyticsurl-utils) | parse URLs, read/scrub UTM params |
| [`@analytics/router-utils`](#analyticsrouter-utils) | fire a page view on SPA route change |
| [`@analytics/listener-utils`](#analyticslistener-utils) | attachable/detachable DOM listeners; hook `onerror`/`onload` safely |
| [`@analytics/activity-utils`](#analyticsactivity-utils) | engaged time, idle detection, heartbeats |
| [`@analytics/scroll-utils`](#analyticsscroll-utils) | scroll-depth events |
| [`@analytics/queue-utils`](#analyticsqueue-utils) | batch events and flush on an interval |
| [`@analytics/redact-utils`](#analyticsredact-utils) | obfuscate PII-ish fields in a payload |
| [`@analytics/type-utils`](#analyticstype-utils) | runtime type guards + env flags without lodash |
| [`use-analytics`](#use-analytics) | React context/hooks — see `frameworks-and-spa.md` |

## `@analytics/storage-utils`

The same API exposed on the instance as `analytics.storage`. Falls back **localStorage → cookies → sessionStorage → global window**, so it keeps working in Safari private mode and other hostile environments.

```js
import { setItem, getItem, removeItem } from '@analytics/storage-utils'

setItem('key', 'value')
// → { value: 'value', oldValue: 'old', location: 'localStorage' }

setItem('keyTwo', 'cookieVal', { storage: 'cookie' })

getItem('key', { storage: 'localStorage' })
getItem('otherKey', { storage: '*' })   // { cookie: undefined, localStorage: 'hahaha', global: null }

removeItem('otherKey', { storage: '*' })
```

`storage` option: `'localStorage' | 'cookie' | 'sessionStorage' | 'global' | '*'`. `setItem` returns where the value actually landed — worth logging when you're debugging a value that "isn't persisting."

## Single-mechanism storage

```js
import { hasLocalStorage, getItem, setItem, removeItem } from '@analytics/localstorage-utils'

import { hasSessionStorage, getSessionItem, setSessionItem, removeSessionItem }
  from '@analytics/session-storage-utils'   // note the distinct names — importable alongside the above

import { globalContext, get, set, remove, wrap, hasSupport }
  from '@analytics/global-storage-utils'
```

`wrap(storageType, method, fallbackFn)` builds a guarded accessor: `const safeGet = wrap('localStorage', 'getItem', () => null)`.

## `@analytics/cookie-utils`

```js
import { hasCookies, setCookie, getCookie, removeCookie } from '@analytics/cookie-utils'

setCookie(name, value, ttl, path, domain, secure)
setCookie('test', 'a', 60 * 60 * 24, '/api', '*.example.com', true)
getCookie('test')
removeCookie('test')
```

`hasCookies()` actually round-trips a cookie to check the browser accepts one, rather than trusting `navigator.cookieEnabled`.

## `@analytics/remote-storage-utils`

Read/write localStorage **across domains you control**, via a hub iframe — the way to share an anonymous ID between `site.com` and `app.site.com`.

```js
import { RemoteStorage, CrossStorageHub } from '@analytics/remote-storage-utils'

// on the client
const storage = new RemoteStorage('https://remote-site.com/storage.html')
await storage.setItem({ key: 'shared_id', value: 'abc' })
const id = await storage.getItem('shared_id')

// on the hub page (storage.html)
CrossStorageHub.init([
  { origin: /\.example.com$/, allow: ['get', 'set', 'del'] }
])
```

`setRemoteItem` takes an optional `resolve({ key, local, remote, isEqual })` conflict resolver; return a value to write, or `undefined` to abort.

## `@analytics/form-utils`

Tracks submits/changes **and filters sensitive values by default** (`disableFilter: false`). `onSubmit` intercepts the submission, runs your callback, then submits normally. Every listener returns a cleanup function.

```js
import { onSubmit, listen, getFormData, filterData } from '@analytics/form-utils'

const cleanUp = onSubmit('form[id=signup]', {
  excludeFields: [/private/, 'ssn'],
  filter: (fieldName, value) => {
    if (value.match(/^\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}$/)) return false  // credit card
    return true   // return false to EXCLUDE the field
  }
}, (event, data) => {
  analytics.track('formSubmitted', data)
})

onSubmit('all', (event, data) => {})   // every form on the page

listen({
  onSubmit: (event, data) => {},
  onChange: (event, data) => {},
  includeForms: ['form[id=content-form]'],
  excludeForms: ['form[name=two]']
})
```

`debug: true` stops the form actually submitting so you can inspect what would be sent. Sending a whole form payload to a third party without thinking about the field list is how passwords end up in an analytics vendor.

## `@analytics/url-utils`

```js
import { parseUrl, getSearch, getSearchValue, removeSearch, getDomain, isExternal }
  from '@analytics/url-utils'

parseUrl('https://www.cool.com/my-path?hello=true#my-hash=cool')
// { href, protocol: 'https',  ← no trailing colon
//   hostname: 'www.cool.com', port: '', pathname: '/my-path',
//   search: 'hello=true',     ← no leading ?
//   hash: 'my-hash=cool' }

getSearch()                  // reads window.location.search → object
getSearchValue('utm_source')
removeSearch(/^utm_/)        // with NO url arg, rewrites the address bar via the history API
```

Also: `isUrl`, `isUrlLike`, `isInternal`, `isExternal`, `isLocalHost`, `getLocation`, `getHost`, `getUrl`, `getSubDomain`, `trimTrailingSlash`, `trimTld`, `getHash`, `getHashValue`, `removeHash`, `getParams`, `removeParams`, `compressParams`/`decompressParams`, `complexParseSearch`/`complexParseHash`/`complexParseParams`.

The no-argument form of `removeSearch`/`removeHash` mutating browser history is the surprising one — convenient for scrubbing UTMs, alarming if you didn't expect it.

## `@analytics/router-utils`

Default export. Listens for `pushState`. See `frameworks-and-spa.md`.

```js
import onRouteChange from '@analytics/router-utils'

onRouteChange((newRoutePath) => analytics.page())
```

## `@analytics/listener-utils`

```js
import { addListener, removeListener, once, addWindowEvent, onError, onLoad }
  from '@analytics/listener-utils'

const disable = addListener('#button', 'click', async () => {
  const reEnable = disable()        // detach → returns a re-attach fn → toggles forever
  await fetch('/api')
  reEnable()
})

addListener('#btn', 'click mouseover', handler)      // space-separated events
addListener('#btn', 'click', handler, { once: true })

onError((message, source, lineno, colno, error) => {})  // preserves any existing window.onerror
onLoad(() => {})                                        // preserves any existing window.onload
addWindowEvent('onresize', () => {})                    // wraps rather than clobbers
```

The `onError`/`onLoad`/`addWindowEvent` wrappers exist because `window.onerror = fn` silently destroys whatever handler was already there — often another analytics tool's.

## `@analytics/activity-utils`

Real engaged time, not "time between first and last event."

```js
import { onIdle, onWakeUp, onUserActivity, onDomActivity } from '@analytics/activity-utils'

const { disable, getStatus } = onUserActivity({
  timeout: 10000,     // ms before considered idle
  throttle: 2000,
  onIdle:      (activeTime) => analytics.track('userIdle',   { activeTime }),
  onWakeUp:    (idleTime)   => analytics.track('userWakeUp', { idleTime }),
  onHeartbeat: (activeTime) => analytics.track('heartbeat',  { activeTime })
})

getStatus()   // { isIdle, isDisabled, active, idle }
```

Watches mouse, touch, keyboard, scroll, load, and tab visibility. A heartbeat that keeps firing in a background tab is the bug this prevents.

## `@analytics/scroll-utils`

```js
import { onScrollChange, getScrollPercent, getScrollDistance, getDocHeight }
  from '@analytics/scroll-utils'

const detach = onScrollChange({
  25: ({ trigger, direction, scrollMin, scrollMax, range }) =>
        analytics.track('scrollDepth', { depth: 25, direction }),
  50: (info) => {},
  75: (info) => {},
  90: (info) => {}
})
```

## `@analytics/queue-utils`

Default export `smartQueue`. Batch events, flush on an interval — for posting to your own endpoint without one request per event.

```js
import smartQueue from '@analytics/queue-utils'

const queue = smartQueue((items, restOfQueue) => sendBatch(items), {
  max: 10,           // items per batch
  interval: 3000,    // ms between batches
  throttle: true,    // overflow waits for the next interval
  onEmpty: (q) => {}
})

queue.push(item)
queue.flush()       // process now
queue.pause(); queue.resume(); queue.size()
```

## `@analytics/redact-utils`

Keys prefixed with `$` get base64-encoded (both key and value), with the encoded keys indexed under a `_` array. Recurses through nested objects.

```js
import { redactObject, restoreObject, cleanObject } from '@analytics/redact-utils'

redactObject({ hi: 'awesome', $email: 'foo@bar.com' })
// { hi: 'awesome', _: ['JGVtYWls'], JGVtYWls: 'Zm9vQGJhci5jb20=' }

restoreObject(encoded)         // → { $email: 'foo@bar.com' }
restoreObject(encoded, true)   // → { email:  'foo@bar.com' }  (strip the $)
cleanObject({ $email: '...' }) // → { email: '...' }  (de-prefix, no decode)
```

**This is obfuscation, not encryption** — base64 is trivially reversible, and the docs say so. It keeps PII from being casually greppable in logs. It is not a compliance control, and reaching for it to "secure" data is a misread of what it does.

## `@analytics/type-utils`

~60 tree-shakable runtime guards and environment flags.

```js
import { isBrowser, isDev, isObject, isEmail, isEmpty, ensureArray, noOp }
  from '@analytics/type-utils'
```

Env flags are **booleans, not functions**: `isProd`, `isStaging`, `isDev`, `isBrowser`, `isNode`, `isDeno`, `isWebWorker`, `isJsDom`, `isLocalHost`.

Guards: `isFunction`, `isString`, `isNumber`, `isNumberLike`, `isArray`, `isObject`, `isObjectLike`, `isJson`, `isPromise`, `isSet`, `isMap`, `isRegex`, `isError`, `isErrorLike`, `isEmail`, `isDate`, `isIsoDate`, `isEmpty`, `isTruthy`/`isFalsy`, `isElement`, `isForm`, `isInput`, `isHidden`, … plus `noOp()` and `ensureArray(value)`.

Two gotchas worth knowing: `isNumber(Infinity)` is **true** (only `NaN` is excluded), and `isTruthy('false')` is **false** — the string is treated as the boolean. Also note `isLocalHost` here is a boolean flag, while `@analytics/url-utils` exports an `isLocalHost(url)` *function*. Easy to conflate.

## `use-analytics`

React provider/hooks. Covered in `frameworks-and-spa.md`.
