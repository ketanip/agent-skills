# meta-pixel

> Ship Meta Pixel tracking that actually feeds your ad optimization — correct events, correct parameter shapes, verified. Because `fbq()` never throws, and a broken pixel looks exactly like a working one.

```bash
npx skills add ketanip/agent-skills --skill meta-pixel
```

> Part of the [ketanip/agent-skills](https://github.com/ketanip/agent-skills) collection — drop `--skill meta-pixel` to install every skill in it. Works with Claude Code, Cursor, Copilot, Windsurf, Cline — any agent that supports [skills.sh](https://skills.sh).

---

## The bug you don't find for six weeks

```js
fbq('track', 'Purchase', {
  value: '5000,00',                    // string with a comma
  currency: '$',                       // symbol, not an ISO code
  contents: [{ id: 'SKU-123' }]        // missing `quantity`
});
```

No error. No warning. No red in the console. The event reaches Events Manager, the page renders fine, and the pull request looks clean.

And your Purchase optimization has nothing to optimize on. Your catalog ads can't match a single product. You find out when someone finally asks why ROAS has been flat for a month.

**Meta's own docs list these as the recurring mistakes.** They're recurring because nothing in the platform tells you you've made them.

---

## What the skill does about it

It treats **parameter shape as the load-bearing part of the job**, not a detail — and it ships a linter so the check is mechanical instead of a matter of anyone's vigilance.

```bash
python skills/meta-pixel/scripts/check_pixel.py src/
```

```
ERROR src/checkout.js:2: value: '5000,00' — must be a number, not a string
ERROR src/checkout.js:2: currency: '$' — must be a 3-letter ISO 4217 code (e.g. 'USD'), not a symbol
ERROR src/checkout.js:2: contents entry {id: 'SKU-123'} is missing the required `quantity` key
ERROR src/tracking.js:4: 2 pixels are initialized in this file, so fbq('track', 'Purchase')
                        fires on ALL of them — use 'trackSingle' with an explicit pixel ID
```

Zero dependencies, Python 3 only, exit code `1` on errors — drops straight into a pre-commit hook or CI step. Useful on its own even if you never install the skill.

---

## The trap nobody knows about until it bites

`fbq('init', ...)` pushes the pixel ID into a **global queue**. Every later `fbq('track', ...)` then fires against **every initialized pixel** — regardless of which `init` it appears after, and regardless of whether the pixels came from two separate base-code blocks pasted in by two different agencies.

```js
fbq('init', 'PIXEL-A');
fbq('track', 'Purchase', {...});   // ← also fires on PIXEL-B
fbq('init', 'PIXEL-B');
fbq('trackCustom', 'Step4');       // ← also fires on PIXEL-A
```

Both agencies' reports are now wrong, and neither has any reason to suspect it. The fix is `trackSingle` / `trackSingleCustom` — and the skill knows to reach for it, and the linter flags the pages that need it.

---

## What your agent learns

| Reference | What it covers |
|---|---|
| **SKILL.md** | Decision table → install → track → verify. Routes to a reference only when the task needs one. |
| **standard-events.md** | All 17 standard events, every object property, `content_ids` vs `contents`, custom conversions (incl. the Sept 2025 flagging rules) |
| **advanced.md** | SPA route-change tracking, click/scroll/visibility/percentage triggers, multi-pixel, `<img>` installs, autoConfig, CSP |
| **privacy-and-consent.md** | Advanced matching + the normalization rules that make it work, GDPR consent API, Limited Data Use for US states |
| **use-cases.md** | Advantage+ catalog ads, Collaborative Ads, Marketing API (`promoted_object`, AEM's 8-event cap), movies |
| **troubleshooting.md** | A diagnosis ladder that starts at "does it load", Pixel Helper, migration off the deprecated pixels |

Loaded on demand. Asking for a purchase event doesn't drag the Collaborative Ads spec into your context.

---

## Just talk to your agent normally

**"Add Meta pixel purchase tracking to our Next.js checkout"**
→ Installs the base code in the layout, fires `Purchase` on the confirmation page — not the button — with `value` as a number and `currency` as an ISO code.

**"Our AddToCart events aren't showing up in Events Manager"**
→ Walks the diagnosis ladder: does the pixel load, does the event fire, is the payload malformed, is it a multi-pixel over-fire.

**"We need the pixel to respect our EU cookie banner"**
→ `fbq('consent', 'revoke')` **before** `init`, on **every** page — the two details that quietly break every hand-rolled consent gate.

**"Catalog ads aren't matching our products"**
→ Goes straight to the `content_ids`-must-match-the-catalog join, the actual cause almost every time.

---

## Honest limits

- The linter is **static analysis over source text**. It cannot tell you whether an event actually fires in a browser. Always confirm with the [Meta Pixel Helper](https://developers.facebook.com/documentation/meta-pixel/support/pixel-helper) — and the skill says so too, rather than letting your agent declare victory.
- Derived from Meta's public [Meta Pixel documentation](https://developers.facebook.com/documentation/meta-pixel). Meta changes this stuff. When reality disagrees with the skill, reality wins.
- Not affiliated with or endorsed by Meta.

---

## Skill details

| | |
|---|---|
| **Skill name** | `meta-pixel` |
| **Collection** | [ketanip/agent-skills](https://github.com/ketanip/agent-skills) |
| **Activation** | Automatic on Meta/Facebook Pixel, `fbq`, conversion tracking, and Events Manager work |
| **Reference files** | 5 focused files, loaded on demand |
| **Bundled tooling** | `check_pixel.py` linter, base-code template |
| **Author** | [Ketan Iralepatil](https://github.com/ketanip) |
