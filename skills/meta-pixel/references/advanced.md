# Advanced Implementation Patterns

## Contents
- [Single Page Applications](#single-page-applications)
- [Button clicks](#button-clicks)
- [Scroll and visibility triggers](#scroll-and-visibility-triggers)
- [Delayed fires and session counters](#delayed-fires-and-session-counters)
- [Multiple pixels](#multiple-pixels)
- [Automatic configuration](#automatic-configuration)
- [Installing with an img tag](#installing-with-an-img-tag)
- [Content Security Policy](#content-security-policy)

## Single Page Applications

An SPA changes the URL without reloading the page, so the base code's `PageView` fires exactly once — on the initial load — and every subsequent "page" is invisible to the pixel unless you say otherwise.

There is no drop-in fix; it depends on the router. The job is always the same shape: **hook the framework's route-change event and fire the appropriate `fbq('track', ...)` there.** In React Router that's a `useEffect` on `location.pathname`; in Next.js it's `router.events.on('routeChangeComplete', ...)`; in Vue Router it's an `afterEach` guard. Map each route to the event it represents rather than firing a blanket `PageView` everywhere, when the route corresponds to a real funnel step.

The docs' vanilla illustration, using the History State API directly:

```js
var loadContent = function(href) {
  $.ajax(href + '.html', {
    success: function(data) {
      history.pushState({url: href}, 'New URL: ' + href, href);
      $('#content').html(data);

      var eventname = null;
      switch (href) {
        case 'link1': eventname = 'ViewContent'; break;
        case 'link2': eventname = 'AddPaymentInfo'; break;
        case 'link3': eventname = 'CompleteRegistration'; break;
        default:
      }
      fbq('track', eventname);
    },
    error: function() { console.log('An error occurred'); }
  });
};
```

The pixel listens for `pushState`/`replaceState` and auto-sends `PageView` on history changes. You can turn that off with `fbq.disablePushState = true` (or `disablePushState: true`), **but the docs recommend against it** — only reach for it when you're certain you're double-counting.

## Button clicks

For actions that don't navigate — "Add to Cart" on a product page — bind the event to the handler. Any binding style works; the only requirement is that `fbq` is called after the click.

```html
<button id="addToCartButton">Add To Cart</button>
<script type="text/javascript">
  var button = document.getElementById('addToCartButton');
  button.addEventListener('click', function() {
    fbq('track', 'AddToCart', {
      content_name: 'Really Fast Running Shoes',
      content_category: 'Apparel & Accessories > Shoes',
      content_ids: ['1234'],
      content_type: 'product',
      value: 4.99,
      currency: 'USD'
    });
  }, false);
</script>
```

Expect the Pixel Helper to show an error on such a page *before* the button is clicked — it assumes on-load firing. Clicking the button clears it. That error is not a bug in your implementation.

## Scroll and visibility triggers

Useful for content sites where "conversion" means the article was actually read. All three helpers below latch — they fire once per page load and then stop.

**When an element scrolls into view:**

```js
var executeWhenElementIsVisible = function(dom_element, callback) {
  if (!(dom_element instanceof HTMLElement)) {
    console.error('dom_element must be a valid HTMLElement');
  }
  if (typeof callback !== 'function') {
    console.error('Second parameter must be a function, got', typeof callback, 'instead');
  }

  function isOnViewport(elem) {
    var rect = elem.getBoundingClientRect();
    var docElem = document.documentElement;
    return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= (window.innerHeight || docElem.clientHeight) &&
      rect.right <= (window.innerWidth || docElem.clientWidth)
    );
  }

  var executeCallback = (function() {
    var wasExecuted = false;
    return function() {
      if (!wasExecuted && isOnViewport(dom_element)) {
        wasExecuted = true;
        callback();
      }
    };
  })();

  window.addEventListener('scroll', executeCallback, false);
};

executeWhenElementIsVisible(document.getElementById('fb-fire-pixel'), function() {
  fbq('track', 'Lead');
});
```

**When a pixel-length of page has been scrolled** — note it fires immediately if the window is already taller than the threshold:

```js
var executeWhenReachedPageLength = function(length, callback) {
  function getWindowLength() {
    return window.innerHeight || (document.documentElement || document.body).clientHeight;
  }
  function getCurrentScrolledLengthPosition() {
    return window.pageYOffset ||
      (document.documentElement || document.body.parentNode || document.body).scrollTop;
  }

  var executeCallback = (function() {
    var wasExecuted = false;
    return function() {
      if (!wasExecuted && getCurrentScrolledLengthPosition() > length) {
        wasExecuted = true;
        callback();
      }
    };
  })();

  if (getWindowLength() >= length) {
    callback();
  } else {
    window.addEventListener('scroll', executeCallback, false);
  }
};

executeWhenReachedPageLength(500, function() { fbq('track', 'Lead'); });
```

**When a percentage of the page has been read** — recomputes the scrollable length on resize, and fires immediately if the whole page already fits on screen:

```js
var executeWhenReachedPagePercentage = function(percentage, callback) {
  function getDocumentLength() {
    var D = document;
    return Math.max(
      D.body.scrollHeight, D.documentElement.scrollHeight,
      D.body.offsetHeight, D.documentElement.offsetHeight,
      D.body.clientHeight, D.documentElement.clientHeight
    );
  }
  function getWindowLength() {
    return window.innerHeight || (document.documentElement || document.body).clientHeight;
  }
  function getScrollableLength() {
    return getDocumentLength() > getWindowLength()
      ? getDocumentLength() - getWindowLength()
      : 0;
  }

  var scrollableLength = getScrollableLength();
  window.addEventListener('resize', function() {
    scrollableLength = getScrollableLength();
  }, false);

  function getCurrentScrolledLengthPosition() {
    return window.pageYOffset ||
      (document.documentElement || document.body.parentNode || document.body).scrollTop;
  }
  function getPercentageScrolled() {
    if (scrollableLength == 0) return 100;
    return getCurrentScrolledLengthPosition() / scrollableLength * 100;
  }

  var executeCallback = (function() {
    var wasExecuted = false;
    return function() {
      if (!wasExecuted && getPercentageScrolled() > percentage) {
        wasExecuted = true;
        callback();
      }
    };
  })();

  if (getDocumentLength() == 0 ||
      (getWindowLength() / getDocumentLength() * 100 >= percentage)) {
    callback();
  } else {
    window.addEventListener('scroll', executeCallback, false);
  }
};

executeWhenReachedPagePercentage(75, function() { fbq('track', 'Lead'); });
```

## Delayed fires and session counters

Filter out bouncers by waiting a few seconds before counting the visit as engaged:

```js
var seconds = 3;
setTimeout(function() { fbq('track', 'Lead'); }, seconds * 1000);
```

Fire on the Nth article of a session, given a server-side session counter:

```js
if (site_request.sessionCountViews == 6) {
  fbq('track', 'ViewContent', {sessionCountViews: site_request.sessionCountViews});
}
```

## Multiple pixels

`fbq('init', ...)` registers the ID in a global queue, and a plain `fbq('track', ...)` fires against **every** initialized pixel. This is true even when the pixels come from two separate base-code blocks — `fbevents.js` only loads once, and the queue is shared. Two agencies each installing their own snippet will each collect the other's events.

```js
fbq('init', '<PIXEL_A>');
fbq('init', '<PIXEL_B>');
fbq('track', 'PageView');  // both, deliberately

fbq('trackSingle', '<PIXEL_A>', 'Purchase', {value: 4, currency: 'GBP'});
fbq('trackSingleCustom', '<PIXEL_B>', 'Step4', {});
```

`trackSingleCustom` does **not** validate custom data — so a typo in a parameter name goes through silently.

## Automatic configuration

By default the pixel sends button-click text and page metadata (OpenGraph, Schema.org) to improve delivery and automate setup. To send only what you explicitly track, disable it — the call must come **before** `init`:

```js
fbq('set', 'autoConfig', false, 'FB_PIXEL_ID');
fbq('init', 'FB_PIXEL_ID');
fbq('track', 'PageView');
```

Worth raising with the user if they're privacy-sensitive: this is what causes form field names and button labels to be collected.

## Installing with an img tag

A fallback for environments that can't run JavaScript. Meta does not recommend it.

```html
<img src="https://www.facebook.com/tr?id={pixel-id}&ev={standard-event}"
     height="1" width="1" style="display:none"/>
```

Parameters go in the query string as `cd[...]`:

```html
<img src="https://www.facebook.com/tr?id=12345&ev=ViewContent&cd[content_name]=ABC%20Leather%20Sandal&cd[content_category]=Shoes&cd[content_type]=product&cd[content_ids]=1234&cd[value]=0.50&cd[currency]=USD"
     height="1" width="1" style="display:none"/>
```

Limitations that make this a last resort: cannot fire more than once per page load, cannot track UI-triggered events like clicks, subject to HTTP GET URL-length limits, and cannot load asynchronously.

## Content Security Policy

Allow scripts from `https://connect.facebook.net`. The pixel pulls from two paths there: `/en_US/fbevents.js` and `/signals/config/{pixelID}?v={version}`.
