# Consent, Privacy & Legal Constraints

**Nothing in this file is legal advice.** Legal status here is unsettled, jurisdiction-specific, and moving. Engage privacy counsel for your verticals and jurisdictions. This file exists so you know *which* questions to take to them and don't ship an architecture that forecloses the answers.

The framing that matters: **"all the data we can" legally is far less than "all the data we technically can."** The tag config is not the binding constraint — consent and litigation are.

## Contents

- [Consent Mode v2](#consent-mode-v2)
- [The two failures that survive testing](#the-two-failures-that-survive-testing)
- [GDPR / ePrivacy](#gdpr--eprivacy)
- [US state laws, GPC, LDU](#us-state-laws-gpc-ldu)
- [Health and sensitive data](#health-and-sensitive-data)
- [Platform policy limits](#platform-policy-limits)
- [Compliant maximum vs. technically possible](#compliant-maximum-vs-technically-possible)

## Consent Mode v2

Four signals: **`ad_storage`**, **`analytics_storage`** (v1), plus **`ad_user_data`** and **`ad_personalization`** (added v2, Nov 2023). Also `functionality_storage`, `personalization_storage`, `security_storage`.

**Default then update.** Set every signal to `denied` **before the GTM container loads**, then `gtag('consent', 'update', {…})` after the user chooses:

```html
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){ dataLayer.push(arguments); }

  gtag('consent', 'default', {
    ad_storage:            'denied',
    ad_user_data:          'denied',
    ad_personalization:    'denied',
    analytics_storage:     'denied',
    functionality_storage: 'granted',
    security_storage:      'granted',
    wait_for_update: 500
  });

  gtag('set', 'ads_data_redaction', true);   // redact click ids while ad_storage denied
  gtag('set', 'url_passthrough', true);      // pass gclid via URL rather than cookie
</script>
<!-- GTM container snippet goes AFTER this -->
```

Ordering is the whole point and it is not recoverable after the fact: a tag that fires before the default is set has already fired. There's no undo, no warning, and the page looks identical. In the container, **Consent Initialization – All Pages** always runs first.

Consent state is encoded to Google in the `gcs` (ad_storage/analytics_storage) and `gcd` (all four, plus how they were derived) URL parameters — `gcs=G100` is the denied-ping signature you'll see in the Network tab.

**Basic vs Advanced:**

| | Basic | Advanced |
|---|---|---|
| Before consent | Google tags don't load at all — no pings | Tags load, send cookieless pings |
| Modeling input | None | Pings feed conversion/behavioral modeling |
| Trade-off | Cleanest posture; you lose the denied population entirely | Better modeling; a network call to Google happens pre-consent |

Advanced sends a cookieless ping before the user has chosen. Google's position is that this is by design and carries no identifiers; some EU DPAs take a stricter view of *any* pre-consent call to a US endpoint. That's a call for your DPO, not for the implementer.

**EEA enforcement:** formally mandatory since **6 March 2024** for Google Ads/GA4 use in the EEA/UK (driven by the Digital Markets Act). Google began actively enforcing on **21 July 2025**, restricting conversion tracking and audience creation for non-compliant accounts. A Google-certified CMP is required for modeling. Behavioral modeling has threshold volumes (Google cites e.g. ≥1,000 daily events with `analytics_storage=denied` over 7 days) and cannot model under IAB TCF denial.

> **Labeled estimate, not a specification:** you will see claims that Consent Mode recovers 15–25% of otherwise-lost conversions, and Google marketing has cited up to ~70% conversion-loss recovery. These are **vendor-marketing and practitioner figures**. Google does not publish an exact recovery rate, and it varies by traffic mix and consent rate. Don't build a business case on them or promise them to a client.

## The two failures that survive testing

Both of these pass every functional test, because the events keep arriving.

**1. Custom HTML tags ignore Consent Mode.** A GA4 tag respects `analytics_storage` natively. A Custom HTML tag containing `fbq()` respects nothing — it fires when its trigger says so. Set **Consent Settings → Require additional consent for: `ad_storage`, `ad_user_data`, `ad_personalization`** on every Meta tag, explicitly. See `references/gtm-container-config.md`.

**2. CAPI bypasses the browser, so it bypasses the consent gate.** This is the one that scales into a real problem, because it's architectural rather than a checkbox. Your webhook fires hours after the visit with no browser to ask. It will happily send a declined user's hashed email to Meta.

Persist the consent decision at collection time and check it server-side:

```js
order.consent = {
  ad_storage:         getConsentState('ad_storage'),
  ad_user_data:       getConsentState('ad_user_data'),
  ad_personalization: getConsentState('ad_personalization'),
  analytics_storage:  getConsentState('analytics_storage'),
  tcf_string:         getTcString(),          // IAB TCF v2.2 string, as evidence
  captured_at:        new Date().toISOString()
};
```

```js
if (order.consent?.ad_user_data !== 'granted') return { skipped: 'no_consent' };
```

Keep it for the accountability obligation (GDPR Art. 5(2)) — you must be able to demonstrate consent existed for any given event you sent. "The CMP was configured correctly at the time" is not evidence about a specific event.

**Hashing is pseudonymization, not anonymization.** A hashed email is still personal data under GDPR. Moving a call server-side changes the transport, not the lawful basis. Server-side is not a consent workaround, and treating it as one is the single most common misconception in this architecture.

## GDPR / ePrivacy

- **Prior consent.** ePrivacy Art. 5(3) requires consent *before* non-essential cookies/identifiers are set. **GA4 in `<head>` firing before a footer banner is the single most common violation** — and it looks perfect in every dashboard.
- **Reject must be as easy as accept**, and no pre-ticked boxes.
- **IP handling:** GA4 does not log or store EU IP addresses (positioned as a GDPR response), but IP is still processed transiently. `client_ip_address` is personal data, and it's required for good CAPI match rates — so your lawful basis for it is consent.
- **DPA:** a Data Processing Agreement/Amendment with Google (and Meta) is mandatory (Art. 28). The Google DPA acceptance is frequently un-clicked on older accounts — check it.
- **Joint controllership with Meta** for pixel/CAPI collection follows from CJEU *Fashion ID* (C-40/17) and *Wirtschaftsakademie* (C-210/16). Accept the Controller Addendum in Business Manager and reflect it in your privacy policy.
- **Transfers / Schrems II / DPF:** after Schrems II (2020) several DPAs (Austria Jan 2022, France Feb 2022, Italy June 2022, Denmark, Norway — final decision Jan 2025) found GA use unlawful over US transfers. The **EU-US Data Privacy Framework** (adequacy decision 10 July 2023; Google and Meta certified) is the current basis. Its durability is contested: a General Court challenge was dismissed Sept 2025 but is on appeal to the CJEU (**Case C-703/25 P, pending**), and the US PCLOB's reduced quorum raises "Schrems III" risk.

Practical posture: rely on DPF + SCCs + DPA now, and keep an EU-hosting contingency (sGTM in an EU region, anonymization) that you could actually execute. If the DPF is struck down, that contingency is the plan.

- **Privacy policy** must name Meta and Google, the purposes, the hashed-identifier practice, the transfer basis, and how to withdraw consent (a persistent link that reopens the CMP).
- **Retention:** GA4 user-data retention defaults to **2 months**, max 14. Set it deliberately. Build the deletion path before the first DSAR arrives — GA4 User Deletion API (by `user_id`) and Meta's deletion endpoint (by hashed `external_id`).

## US state laws, GPC, LDU

CCPA/CPRA and successors (Virginia, Colorado, Connecticut, Maryland MODPA effective Oct 2025, …) use an **opt-out** model, not opt-in. Honor **Global Privacy Control** signals and "Do Not Sell or Share".

Configure **Meta LDU** (`data_processing_options: ["LDU"]`) and **GA4 Restricted Data Processing** for opted-out users. LDU is a **US mechanism** — it does nothing for GDPR, and reaching for it as an EU control is a category error. Details in `references/meta-capi.md`.

**Wiretapping / CIPA:** website-tracking class actions have expanded sharply, treating pixels and session replay as "pen registers" or "wiretaps". California's CIPA carries **$5,000 per violation** (or treble actual damages); federal ECPA up to **$10,000**. 2025 rulings split: pro-plaintiff *Camplisson v. Adidas* (S.D. Cal., Nov 2025) and the *Flo Health* jury verdict (N.D. Cal., Aug 2025 — Meta held liable under CIPA §632 for real-time interception of reproductive-health data); defense-favorable *Torres v. Prudential*, *Price v. Headspace*. California SB 690 (a commercial-purpose exemption) stalled into a 2-year bill.

> **Labeled estimate:** claim counts in the "tens of thousands since 2022" (one vendor tracker cites "50,000+") come from **law-firm and vendor trackers, not an official register**. Treat the direction as real and the number as unverified.

**VPPA:** video pixels on sites with video content trigger Video Privacy Protection Act claims; there's a circuit split on who counts as a "consumer".

If you take California traffic: wire GPC, LDU, and RDP; block third-party pixels until affirmative consent; and name the Meta Pixel explicitly in your privacy policy.

## Health and sensitive data

The highest-consequence area in this stack, and the one where the right answer is often "don't".

- **HIPAA/FTC/OCR:** OCR's Dec 2022 bulletin warned that pixels on patient portals and health sites may unlawfully disclose PHI; a July 2023 joint FTC-OCR letter went to ~130 hospital and telehealth providers. FTC enforcement hit **GoodRx** (Feb 2023), **BetterHelp** (Mar 2023), and **Premom**. *In re Meta Pixel Healthcare Litigation* (N.D. Cal.) alleges the Pixel intercepted PHI from 600+ hospital web properties; the court compelled a limited deposition of Mark Zuckerberg (April 2025).
- **Meta auto-restricts health/wellness data sources** into three tiers — see `references/meta-capi.md` → restricted categories. You don't get to opt out of the categorization.

If your site touches health, financial, or other sensitive categories:

- Do **not** send event-level identity or content to Meta on those paths.
- Strip sensitive tokens from URLs, event names, and custom params — including inferences. A `content_ids` of pharmacy SKUs is health data; an `item_name` can imply a diagnosis.
- Expect Meta auto-restriction regardless of what you intend.
- Consider not running the Pixel at all on those paths. That is a legitimate engineering answer, and frequently the correct one.
- Get counsel involved before, not after.

## Platform policy limits

Even where the tools physically allow it:

- **Google:** no PII in parameters, user properties, user IDs, or URLs. Hashed UPD is the only personal-data channel. Advertising Features require consent. Violations risk **data deletion and account action**.
- **Meta:** contact info must be SHA-256 hashed. No health, financial, or other sensitive categories. No SSNs or card numbers. Nothing from or about under-13s. Health/wellness sources auto-restricted.

## Compliant maximum vs. technically possible

| Dimension | Technically possible | Compliant maximum |
|---|---|---|
| Behavioral / commerce events | Everything, always-on | Everything, **consent-gated** (Consent Mode + certified CMP) |
| Identity | Raw email/phone/name in params and URLs | **Hashed** — UPD (GA4) / Advanced Matching + CAPI (Meta) only |
| Special-category data | Health, financial, precise conditions | **Never** — strip from URLs, event names, custom params |
| Architecture | Client-side, direct to every vendor | **Server-side (sGTM)** with param stripping, EU hosting, consent enforcement |
| Transfers | US endpoints | DPF + SCCs + DPA; EU-region endpoints where possible |

The defensible implementation collects the maximum **behavioral/commercial** data under consent, restricts **identity** to hashed sanctioned channels, and sends **no** special-category data — regardless of what the tools would physically allow.
