#!/usr/bin/env python3
"""Lint Meta Conversions API payload construction for the mistakes that return 200.

Usage:
    python3 check_capi.py <file-or-dir> [<file-or-dir> ...]
    python3 check_capi.py --self-test

Exit codes: 0 = clean, 1 = errors found, 2 = bad invocation.

The Conversions API returns 2xx when a payload is *valid*, not when it is *usable*.
A SHA-256 of an un-normalized email, a hashed fbp, a fabricated fbc, a missing
action_source -- all accepted, all reported as events_received: 1, all matching
nobody. This linter catches the mechanical half of that: patterns that are wrong
by inspection, per Meta's documented rules.

Catches:
  * hashing a do-not-hash field (fbc/fbp/client_ip_address/client_user_agent/...)
  * sending a must-hash field (em/ph/fn/...) raw
  * fabricated fbc placeholders -- inventing a click ID that cannot match
  * missing action_source / event_id in an events payload
  * name/city normalizers that strip non-Roman characters (Meta's own vector is
    the Korean name "jeong"; [^a-z] scrubbing hashes an empty string)
  * unconditional 5-char zip truncation (a US-only rule)
  * currency as a lowercase/symbol literal, value as a string literal
  * hashing a possibly-empty string
  * event_time computed as upload time rather than transaction time
  * request timeouts far above the documented 1500 ms recommendation
  * test_event_code that looks hard-coded rather than env-gated

This is static analysis over source text. It cannot tell you whether an event
matched a user -- only Events Manager (matched/attributed counts, EMQ) can.
"""

import re
import sys
from pathlib import Path

# Meta: "Hashing required" / "Hashing recommended"
MUST_HASH = {"em", "ph", "fn", "ln", "ge", "db", "ct", "st", "zp", "country"}
SHOULD_HASH = {"external_id"}

# Meta: "Do not hash."
NEVER_HASH = {
    "fbc", "fbp", "client_ip_address", "client_user_agent", "subscription_id",
    "fb_login_id", "lead_id", "anon_id", "madid", "page_id",
    "page_scoped_user_id", "ctwa_clid", "ig_account_id", "ig_sid",
}

HASH_CALL = r"(?:sha256|sha_256|hash|hashed|hashSHA256|sha256Hash|_hash|digest)"

SOURCE_SUFFIXES = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py", ".rb", ".php",
    ".go", ".java", ".kt", ".cs", ".vue", ".svelte", ".astro",
}

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", "vendor",
    "__pycache__", ".venv", "venv", "target", ".tox",
}

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"


class Finding:
    def __init__(self, path, line, level, message):
        self.path, self.line, self.level, self.message = path, line, level, message

    def __str__(self):
        return f"{self.level} {self.path}:{self.line}: {self.message}"


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def strip_comments(text):
    """Blank out // and # line comments so commented-out code doesn't trip rules."""
    out = []
    for line in text.split("\n"):
        s = line.lstrip()
        if s.startswith("//") or s.startswith("#"):
            out.append("")
        else:
            out.append(line)
    return "\n".join(out)


def looks_like_capi(text):
    """Only lint files that actually touch the Conversions API."""
    return bool(
        re.search(r"/events\b", text) and re.search(r"graph\.facebook\.com", text)
    ) or bool(re.search(r"\b(event_name|user_data|action_source|test_event_code)\b", text))


def _balanced(text, open_idx, opener="{", closer="}"):
    """Return the index just past the bracket opened at open_idx, string-aware."""
    depth, i, n = 0, open_idx, len(text)
    in_str, quote, esc = False, "", False
    while i < n:
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        elif ch in "\"'`":
            in_str, quote = True, ch
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def user_data_regions(text):
    """Yield (start, end) offsets of each user_data object literal.

    Matches `user_data: {`, `user_data = {`, and wrapped forms such as
    `const user_data = dropUndefined({`. Field rules run ONLY inside these
    regions -- a caller passing `country: order.country` into its own options
    object is not building user_data, and flagging it is a false positive.
    """
    for m in re.finditer(r"""['"]?\buser_data\b['"]?\s*[:=]""", text):
        brace = text.find("{", m.end())
        if brace == -1:
            continue
        # Only accept a '{' that is part of this assignment (allow a wrapper
        # call like dropUndefined( in between, but not a whole other statement).
        between = text[m.end():brace]
        if ";" in between or "\n\n" in between or len(between) > 60:
            continue
        yield brace, _balanced(text, brace)


def value_expr(text, start):
    """Extract the full value expression beginning at `start` (just past a colon),
    stopping at a depth-0 comma or a newline that ends the entry."""
    depth, i, n = 0, start, len(text)
    in_str, quote, esc = False, "", False
    while i < n:
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        elif ch in "\"'`":
            in_str, quote = True, ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif ch == "," and depth == 0:
            break
        elif ch == "\n" and depth == 0:
            break
        i += 1
    return text[start:i].strip()


# --- rules ---------------------------------------------------------------


def check_never_hash(text, path, out):
    """fbc/fbp/client_ip_address/... must be sent raw. Hashing them is the
    highest-cost silent failure on this API.

    Not scoped to user_data: hashing these is wrong wherever it appears, and
    they are often assembled in a separate `signals` object.
    """
    for field in sorted(NEVER_HASH):
        pat = re.compile(
            r"""['"]?\b%s\b['"]?\s*[:=]\s*(?:\[\s*)?%s\s*\(""" % (field, HASH_CALL)
        )
        for m in pat.finditer(text):
            why = {
                "fbc": "fbc carries the click ID that ties this conversion to the ad -- "
                       "hashing it destroys your strongest attribution signal",
                "fbp": "fbp is the browser ID used for cross-session identity and as a "
                       "dedup/external-id fallback",
                "client_ip_address": "Meta: the client_ip_address parameter 'must never be hashed'",
                "client_user_agent": "client_user_agent is a raw match signal and is required "
                                     "for website events",
            }.get(field, "Meta's parameter table marks this field 'Do not hash'")
            out.append(Finding(
                path, line_of(text, m.start()), ERROR,
                f"`{field}` is hashed but must be sent raw. {why}. "
                f"The API still returns 200 events_received:1 -- it just never matches.",
            ))


def check_must_hash(text, path, out):
    """em/ph/fn/... must be normalized + SHA-256'd before sending.

    Scoped to user_data regions only, and evaluates the WHOLE value expression --
    `customer.id ? sha256(String(customer.id)) : undefined` is hashed, even though
    its first token isn't.
    """
    hex64 = re.compile(r"^['\"][0-9a-fA-F]{64}['\"]$")
    for start, end in user_data_regions(text):
        region = text[start:end]
        for field in sorted(MUST_HASH | SHOULD_HASH):
            pat = re.compile(r"""['"]?\b%s\b['"]?\s*:\s*""" % field)
            for m in pat.finditer(region):
                expr = value_expr(region, m.end())
                if not expr:
                    continue
                # Hashed anywhere in the expression (call, ternary, member, spread).
                if re.search(HASH_CALL, expr, re.I):
                    continue
                # A literal digest, or a list of them.
                if hex64.match(expr.strip("[] ")):
                    continue
                if expr in {"None", "null", "undefined", "True", "False", "..."}:
                    continue
                if expr.startswith("...") or expr.startswith("**"):
                    continue
                level = ERROR if field in MUST_HASH else WARN
                note = (
                    "Meta requires SHA-256 of the *normalized* value; raw PII is rejected "
                    "for matching and should not be sent at all"
                    if field in MUST_HASH else
                    "hashing external_id is recommended -- but whichever form you pick must "
                    "match what the browser Pixel sends, or the two never join"
                )
                shown = expr if len(expr) <= 40 else expr[:37] + "..."
                out.append(Finding(
                    path, line_of(text, start + m.start()), level,
                    f"`{field}` appears to be assigned an unhashed value (`{shown}`). {note}.",
                ))


def check_fabricated_fbc(text, path, out):
    """Inventing an fbc when there is no fbclid manufactures a fake ad-click record."""
    pat = re.compile(
        r"""fb\.\d\.\$?\{?[^'"`\n]*\}?\.(unknown|none|null|placeholder|test|xxx|na)\b""",
        re.I,
    )
    for m in pat.finditer(text):
        out.append(Finding(
            path, line_of(text, m.start()), ERROR,
            f"fabricated `fbc` value ending in '{m.group(1)}'. A synthesized click ID "
            "cannot match and invents an ad-click attribution record for organic/direct "
            "conversions. If there is no _fbc cookie and no fbclid, omit fbc entirely.",
        ))
    # `_fbc || <literal fb....>` fallback
    for m in re.finditer(r"""_fbc\s*(?:\|\||or)\s*[`'"]fb\.""", text):
        out.append(Finding(
            path, line_of(text, m.start()), ERROR,
            "`fbc` falls back to a constructed literal when the _fbc cookie is missing. "
            "Only build fbc from a real fbclid (fb.1.<ms_timestamp>.<fbclid>); otherwise "
            "omit the field.",
        ))


def check_required_fields(text, path, out):
    """action_source is required; event_id is required in practice for dedup."""
    if not re.search(r"""['"]?\bevent_name\b['"]?\s*[:=]""", text):
        return
    first = re.search(r"""['"]?\bevent_name\b['"]?\s*[:=]""", text)
    ln = line_of(text, first.start())
    if not re.search(r"""['"]?\baction_source\b['"]?\s*[:=]""", text):
        out.append(Finding(
            path, ln, ERROR,
            "payload builds an event but never sets `action_source` -- a required "
            "parameter for every Conversions API event (website/app/email/physical_store/...). "
            "By using the API you warrant it is accurate.",
        ))
    if not re.search(r"""['"]?\bevent_id\b['"]?\s*[:=]""", text):
        out.append(Finding(
            path, ln, WARN,
            "no `event_id` set. If the browser Pixel also fires this event, every "
            "conversion is counted twice: dedup requires the Pixel's eventID to equal "
            "event_id and the names to match, within 48 hours. Use the order/transaction ID.",
        ))
    if re.search(r"""['"]?action_source['"]?\s*[:=]\s*['"]website['"]""", text) \
            and not re.search(r"""['"]?\bevent_source_url\b['"]?\s*[:=]""", text):
        out.append(Finding(
            path, ln, WARN,
            "action_source is 'website' but `event_source_url` is not set -- it is "
            "required for website events (as is client_user_agent).",
        ))


def check_event_source_url_is_referrer(text, path, out):
    """event_source_url is the page URL; referrer_url is a separate parameter."""
    pat = re.compile(
        r"""['"]?event_source_url['"]?\s*[:=]\s*[^,\n]*\b(referer|referrer|HTTP_REFERER)\b""",
        re.I,
    )
    for m in pat.finditer(text):
        out.append(Finding(
            path, line_of(text, m.start()), WARN,
            "`event_source_url` is set from the HTTP referrer. event_source_url is the "
            "URL where the event happened (and should match your verified domain); the "
            "referrer has its own parameter, `referrer_url`.",
        ))


def check_normalizers(text, path, out):
    """Normalization regexes that silently delete data."""
    # Stripping non-Roman characters from names/cities.
    for m in re.finditer(r"""replace\s*\(\s*/\[\^a-z(?:A-Z)?\]/g?i?\s*,\s*['"]{2}\s*\)""", text):
        out.append(Finding(
            path, line_of(text, m.start()), ERROR,
            "normalizer strips every non-a-z character. Meta's own published vectors "
            "include the name 'jeong' (Korean) and 'Valery' (accented) -- special "
            "characters must be kept and UTF-8 encoded, not removed. This hashes an "
            "empty string for non-Roman names.",
        ))
    for m in re.finditer(r"""re\.sub\s*\(\s*r?['"]\[\^a-z\]['"]\s*,\s*['"]{2}""", text):
        out.append(Finding(
            path, line_of(text, m.start()), ERROR,
            "normalizer strips every non-a-z character -- see Meta's 'jeong'/'Valery' "
            "vectors. Keep special characters, encode UTF-8.",
        ))
    # Unconditional 5-char zip truncation.
    zip_trunc = re.compile(
        r"""\w*(?:zip|zp|postal|postcode)\w*\s*[:=][^;\n]*?"""
        r"""(?:\.slice\s*\(\s*0\s*,\s*5\s*\)|\[\s*:\s*5\s*\]|\.substring\s*\(\s*0\s*,\s*5\s*\)|\.substr\s*\(\s*0\s*,\s*5\s*\))""",
        re.I,
    )
    for m in zip_trunc.finditer(text):
        out.append(Finding(
            path, line_of(text, m.start()), WARN,
            "zip is truncated to 5 characters unconditionally. Meta's rule is 'use only "
            "the first 5 digits for U.S. zip codes' -- US-only. A UK postcode ('sw1a1aa') "
            "or other non-US format is mangled by this.",
        ))
    # Phone without leading-zero strip is hard to detect reliably; check for a
    # digits-only normalizer that never mentions the country code.
    m = re.search(r"""\bph\b\s*:\s*\[?\s*%s\s*\(""" % HASH_CALL, text)
    if m and not re.search(r"country[_ ]?code|\bE\.?164\b|leading zero", text, re.I):
        out.append(Finding(
            path, line_of(text, m.start()), INFO,
            "`ph` is hashed -- confirm the normalizer removes symbols, letters AND "
            "leading zeros, and that the country code is prepended. Meta: a phone "
            "number must include the country code to be used for matching.",
        ))


def check_empty_hash(text, path, out):
    """sha256("") is a constant that matches nothing."""
    for m in re.finditer(r"""%s\s*\(\s*['"]{2}\s*\)""" % HASH_CALL, text):
        out.append(Finding(
            path, line_of(text, m.start()), ERROR,
            "hashing an empty string. sha256('') is a valid-looking constant digest that "
            "matches nobody. Omit the field when the source value is empty.",
        ))


def check_custom_data(text, path, out):
    """currency/value shape."""
    for m in re.finditer(r"""['"]?currency['"]?\s*[:=]\s*['"]([^'"]+)['"]""", text):
        cur = m.group(1)
        if not re.match(r"^[A-Z]{3}$", cur):
            if re.match(r"^[a-zA-Z]{3}$", cur):
                out.append(Finding(
                    path, line_of(text, m.start()), WARN,
                    f"currency '{cur}' is not an uppercase ISO 4217 code -- use "
                    f"'{cur.upper()}'.",
                ))
            else:
                out.append(Finding(
                    path, line_of(text, m.start()), ERROR,
                    f"currency '{cur}' is not a valid ISO 4217 three-letter code. "
                    "Purchase events require a valid code (e.g. 'USD'), not a symbol.",
                ))
    for m in re.finditer(r"""['"]?value['"]?\s*[:=]\s*['"]([0-9][0-9.,]*)['"]""", text):
        out.append(Finding(
            path, line_of(text, m.start()), ERROR,
            f"`value` is a quoted string ('{m.group(1)}'). Meta specifies a numeric value "
            "representing a monetary amount -- send a JSON number, never a "
            "locale-formatted string.",
        ))


def check_event_time(text, path, out):
    """event_time must be the transaction time, not the upload time."""
    pats = [
        r"""['"]?event_time['"]?\s*[:=]\s*(?:Math\.floor\s*\(\s*)?Date\.now\s*\(\s*\)""",
        r"""['"]?event_time['"]?\s*[:=]\s*int\s*\(\s*time\.time\s*\(\s*\)""",
        r"""['"]?event_time['"]?\s*[:=]\s*time\.time\s*\(\s*\)""",
        r"""['"]?event_time['"]?\s*[:=]\s*(?:datetime\.)?(?:datetime\.)?now\s*\(""",
    ]
    for pat in pats:
        for m in re.finditer(pat, text):
            out.append(Finding(
                path, line_of(text, m.start()), INFO,
                "`event_time` is computed from the current clock -- that is the upload "
                "time. Meta defines event_time as when the conversion actually occurred. "
                "Fine for a synchronous send; wrong for a queue, webhook, or retry, where "
                "you should pass the stored transaction timestamp. Window: 7 days, and one "
                "stale event fails the entire request.",
            ))


def check_timeout(text, path, out):
    """Meta recommends a 1500 ms timeout; most responses are under 600 ms."""
    # `timeout: 5000`, `timeout=5`, `AbortSignal.timeout(5000)`, `.timeout(5000)`
    for m in re.finditer(r"""timeout\s*(?:[:=]\s*|\(\s*)(\d+(?:\.\d+)?)""", text, re.I):
        val = float(m.group(1))
        ms = val * 1000 if val < 100 else val  # seconds vs milliseconds
        if ms > 3000:
            out.append(Finding(
                path, line_of(text, m.start()), INFO,
                f"request timeout is ~{int(ms)} ms. Meta recommends 1500 ms ('the "
                "majority of requests' respond under 600 ms). A long timeout inside a "
                "checkout request makes ad tracking a latency risk to the conversion "
                "itself -- send asynchronously.",
            ))


def check_test_event_code(text, path, out):
    """test_event_code must not ship to production."""
    for m in re.finditer(r"""['"]?test_event_code['"]?\s*[:=]\s*['"]([^'"]+)['"]""", text):
        out.append(Finding(
            path, line_of(text, m.start()), WARN,
            f"`test_event_code` is hard-coded ('{m.group(1)}'). Meta: it 'should be used "
            "only for testing. You need to remove it when sending your production "
            "payload.' Events sent with it are NOT dropped -- they flow into Events "
            "Manager and are used for targeting and measurement. Gate it behind an env var.",
        ))


RULES = [
    check_never_hash, check_must_hash, check_fabricated_fbc, check_required_fields,
    check_event_source_url_is_referrer, check_normalizers, check_empty_hash,
    check_custom_data, check_event_time, check_timeout, check_test_event_code,
]


def check_text(text, path):
    out = []
    if not looks_like_capi(text):
        return out
    cleaned = strip_comments(text)
    for rule in RULES:
        rule(cleaned, path, out)
    return out


def iter_files(targets):
    for t in targets:
        p = Path(t)
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix in SOURCE_SUFFIXES:
                    if not any(part in SKIP_DIRS for part in f.parts):
                        yield f
        else:
            print(f"warning: no such file or directory: {t}", file=sys.stderr)


# --- self-test -----------------------------------------------------------

BAD = """
const payload = { data: [{
  event_name: "Purchase",
  event_time: Math.floor(Date.now() / 1000),
  user_data: {
    em: req.body.email,
    ph: req.body.phone,
    fbp: sha256(req.cookies._fbp),
    fbc: sha256(req.cookies._fbc || `fb.1.${Date.now()}.unknown`),
    client_ip_address: sha256(req.ip),
    client_user_agent: sha256(req.get('user-agent'))
  },
  custom_data: { value: order.total, currency: "usd" }
}], access_token: TOKEN };
await fetch(`https://graph.facebook.com/v18.0/${PIXEL_ID}/events`, {method: 'POST'});
"""

GOOD = """
const payload = { data: [{
  event_name: "Purchase",
  event_time: order.paidAt,
  event_id: order.id,
  action_source: "website",
  event_source_url: order.checkoutUrl,
  user_data: {
    em: [sha256(normEmail(order.email))],
    ph: [sha256(normPhone(order.phone))],  // country_code prepended
    client_ip_address: clientIp(req),
    client_user_agent: req.get('user-agent'),
    ...(fbp && { fbp }),
    ...(fbc && { fbc })
  },
  custom_data: { value: Number(order.total), currency: "USD" }
}] };
await fetch(`https://graph.facebook.com/v25.0/${PIXEL_ID}/events`, {method: 'POST'});
"""

# Regression fixture: both of these were false positives reported by a subagent
# that followed the skill and wrote *correct* code. A linter that fires on correct
# code gets ignored, so they are pinned here.
GOOD_TERNARY_AND_CALLER = """
export function buildPurchaseEvent({ order, customer, signals }) {
  const country = customer.country;
  const user_data = dropUndefined({
    em: hash.em(customer.email),
    ph: hash.ph(customer.phone),
    ct: hash.ct(customer.city),
    zp: hash.zp(customer.zip, country),
    country: hash.country(country),
    external_id: customer.id ? sha256(String(customer.id)) : undefined,
    ...signals,
  });
  return { event_name: 'Purchase', event_time: order.paidAt, event_id: order.id,
           action_source: 'website', event_source_url: order.url, user_data };
}
sendPurchase({
  order,
  customer: {
    id: order.customerId,
    email: order.email,
    phone: order.phone,
    city: order.city,
    country: order.country,
  },
  signals,
});
const literal = { user_data: { em: ["309a0a5c3e211326ae75ca18196d301a9bdbd1a882a4d2569511033da23f0abd"] } };
"""


def self_test():
    bad = check_text(BAD, Path("<bad>"))
    good = check_text(GOOD, Path("<good>"))
    failures = []

    def want(findings, needle, label):
        if not any(needle in f.message for f in findings):
            failures.append(f"expected to catch: {label}")

    want(bad, "`fbp` is hashed", "hashed fbp")
    want(bad, "`fbc` is hashed", "hashed fbc")
    want(bad, "`client_ip_address` is hashed", "hashed client_ip_address")
    want(bad, "`client_user_agent` is hashed", "hashed client_user_agent")
    want(bad, "`em` appears to be assigned an unhashed", "raw em")
    want(bad, "`ph` appears to be assigned an unhashed", "raw ph")
    want(bad, "never sets `action_source`", "missing action_source")
    want(bad, "no `event_id` set", "missing event_id")
    want(bad, "not an uppercase ISO 4217", "lowercase currency")
    want(bad, "upload time", "event_time as upload time")

    errs = [f for f in good if f.level == ERROR]
    if errs:
        failures.append("false positives on the good payload: " +
                        "; ".join(f.message for f in errs))

    # No finding of ANY level may fire on correct code.
    regression = check_text(GOOD_TERNARY_AND_CALLER, Path("<good-2>"))
    noise = [f for f in regression
             if "external_id" in f.message or "`country`" in f.message
             or "`em`" in f.message or "`ph`" in f.message or "`ct`" in f.message]
    if noise:
        failures.append("false positives on ternary/caller/literal-digest fixture: " +
                        "; ".join(f"{f.line}:{f.message[:70]}" for f in noise))

    print(f"BAD payload  -> {len(bad)} findings "
          f"({sum(1 for f in bad if f.level == ERROR)} errors)")
    for f in bad:
        print(f"  {f.level:5} {f.message[:88]}")
    print(f"GOOD payload -> {len(good)} findings "
          f"({len(errs)} errors)")
    for f in good:
        print(f"  {f.level:5} {f.message[:88]}")

    if failures:
        print("\nSELF-TEST FAILED:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nself-test passed")
    return 0


def main(argv):
    if len(argv) >= 1 and argv[0] == "--self-test":
        return self_test()
    if not argv:
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2

    findings = []
    for f in iter_files(argv):
        try:
            findings.extend(check_text(f.read_text(encoding="utf-8", errors="replace"), f))
        except OSError as e:
            print(f"warning: cannot read {f}: {e}", file=sys.stderr)

    findings.sort(key=lambda f: (str(f.path), f.line))
    for f in findings:
        print(f)

    errors = sum(1 for f in findings if f.level == ERROR)
    if findings:
        warns = sum(1 for f in findings if f.level == WARN)
        infos = sum(1 for f in findings if f.level == INFO)
        print(f"\n{errors} error(s), {warns} warning(s), {infos} note(s)", file=sys.stderr)
        print("Reminder: a 200 with events_received:1 is not proof an event is usable. "
              "Verify in Events Manager (matched/attributed, EMQ).", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
