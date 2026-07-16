#!/usr/bin/env python3
"""Lint GTM dataLayer pushes and Meta CAPI payloads for the patterns that fail silently.

Usage:
    python check_tracking.py <file-or-dir> [<file-or-dir> ...]

Exit codes: 0 = clean, 1 = errors found, 2 = bad invocation.

Catches the mistakes that neither GTM, GA4, nor Meta will ever report:
  * event_id generated randomly instead of derived  -> Pixel/CAPI never deduplicate
  * ecommerce push with no preceding {ecommerce: null} -> items bleed between events
  * content_ids as numbers instead of strings -> catalog ads match nothing
  * PII pre-hashed in the dataLayer -> GA4 Enhanced Conversions silently receives nothing
  * fbp/fbc/ip/user_agent hashed -> the strongest match signals destroyed
  * plaintext email/phone in a CAPI user_data -> unhashed PII to Meta
  * value as a string, currency as a symbol
  * GA4 event names over 40 chars or with illegal characters
  * num_items outside InitiateCheckout, leftover test_event_code
  * the GTM snippet loading before the Consent Mode default

This is static analysis over source text. It cannot tell you whether an event
actually fired, nor whether the browser and server agree at runtime -- always
confirm dedup in Meta Events Manager ("1 event from 2 sources").

Known blind spot, by design: the event_id check flags randomness written INLINE
(`event_id: crypto.randomUUID()`), which is mechanically wrong every time. It does
not flag `const id = crypto.randomUUID()` -- that is the correct mint-and-pass
pattern when `id` is sent to the server in the same request, and a silent
double-count when it isn't. Distinguishing them means following a request body
across a network boundary, which static analysis cannot do. A clean run here is
not evidence that dedup works.
"""

import re
import sys
from pathlib import Path

SOURCE_SUFFIXES = {
    ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".vue", ".svelte",
    ".php", ".erb", ".liquid", ".hbs", ".ejs", ".astro", ".mdx", ".py", ".rb",
}

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", "vendor",
    "__pycache__", "coverage", ".venv", "venv",
}

# GA4 ecommerce events that carry an items[] array and therefore need clearing.
ECOMMERCE_EVENTS = {
    "view_item_list", "select_item", "view_item", "add_to_cart",
    "remove_from_cart", "view_cart", "add_to_wishlist", "begin_checkout",
    "add_shipping_info", "add_payment_info", "purchase", "refund",
    "view_promotion", "select_promotion",
}

# Fields Meta requires to arrive raw. Hashing them destroys the signal silently.
NEVER_HASH = {"fbp", "fbc", "client_ip_address", "client_user_agent",
              "subscription_id", "fb_login_id", "lead_id", "page_id"}

RANDOM_ID_CALL = re.compile(
    r"\b(?:crypto\s*\.\s*randomUUID|uuidv4|uuid\s*\.\s*v4|nanoid|Math\s*\.\s*random"
    r"|secrets\s*\.\s*token_hex|uuid\s*\.\s*uuid4|SecureRandom\s*\.\s*uuid)\s*\(",
    re.I,
)
HASH_CALL = re.compile(r"\b(?:sha256|sha_256|hashSync|createHash|digest|hashlib)\b", re.I)
HEX64 = re.compile(r"['\"][0-9a-f]{64}['\"]", re.I)
GA4_EVENT_NAME_OK = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
EMAILISH = re.compile(r"['\"][^'\"@\s]+@[^'\"@\s]+\.[a-z]{2,}['\"]", re.I)


class Finding:
    def __init__(self, path, line, level, message):
        self.path = path
        self.line = line
        self.level = level
        self.message = message

    def __str__(self):
        return f"{self.level} {self.path}:{self.line}: {self.message}"


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def balanced_args(text, open_paren_idx):
    """Return (args_source, end_index) for a call whose '(' is at open_paren_idx."""
    depth, i, n = 0, open_paren_idx, len(text)
    in_str, quote, esc = False, "", False
    while i < n:
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                in_str = False
        else:
            if c in "'\"`":
                in_str, quote = True, c
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return text[open_paren_idx + 1:i], i
        i += 1
    return None, n


def iter_calls(text, name_pattern):
    """Yield (start_offset, args_source) for each matching call, paren-balanced."""
    for m in re.finditer(name_pattern, text):
        args, _ = balanced_args(text, m.end() - 1)
        if args is not None:
            yield m.start(), args


def key_value(args, key):
    """Crude value extractor for `key: <value>` up to the next comma at depth 0."""
    m = re.search(r"[{,\s]" + re.escape(key) + r"\s*:", args)
    if not m:
        return None
    i, n = m.end(), len(args)
    depth, in_str, quote, esc = 0, False, "", False
    out = []
    while i < n:
        c = args[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                in_str = False
        else:
            if c in "'\"`":
                in_str, quote = True, c
                out.append(c)
            elif c in "[{(":
                depth += 1
                out.append(c)
            elif c in "]})":
                if depth == 0:
                    break
                depth -= 1
                out.append(c)
            elif c == "," and depth == 0:
                break
            else:
                out.append(c)
        i += 1
    return "".join(out).strip()


def has_key(args, key):
    return re.search(r"[{,\s]" + re.escape(key) + r"\s*:", args) is not None


def check_event_id(path, text, offset, args, findings, ctx):
    for key in ("event_id", "eventID"):
        val = key_value(args, key)
        if val and RANDOM_ID_CALL.search(val):
            findings.append(Finding(
                path, line_of(text, offset), "ERROR",
                f"{key} is randomly generated ({val.strip()[:40]}) in {ctx} -- the browser and "
                "server will each produce a different value, so Meta never deduplicates and "
                "every conversion double-counts. Derive it from shared state "
                "(e.g. `purchase.${order.id}`), or mint it once and pass it to the server.",
            ))


def check_hashing(path, text, offset, args, findings, in_datalayer):
    # fbp/fbc/ip/ua must never be hashed.
    for field in NEVER_HASH:
        val = key_value(args, field)
        if val and HASH_CALL.search(val):
            findings.append(Finding(
                path, line_of(text, offset), "ERROR",
                f"`{field}` is being hashed -- Meta requires it raw. Hashing it destroys the "
                "signal with no error; it is one of the strongest match parameters you have.",
            ))

    if not in_datalayer:
        return

    # Pre-hashed PII inside a dataLayer push kills GA4 Enhanced Conversions.
    if HASH_CALL.search(args) or HEX64.search(args):
        for field in ("em", "ph", "email", "phone", "phone_number", "user_data",
                      "fn", "ln", "external_id"):
            val = key_value(args, field)
            if val and (HASH_CALL.search(val) or HEX64.search(val)):
                findings.append(Finding(
                    path, line_of(text, offset), "ERROR",
                    f"`{field}` looks pre-hashed in a dataLayer push. The dataLayer must carry "
                    "PLAINTEXT: the GA4 User-Provided Data variable and fbevents.js hash at send "
                    "time. A 64-char digest silently disables Enhanced Conversions. Hash only at "
                    "the CAPI server boundary.",
                ))
                break


def check_ecommerce_shape(path, text, offset, args, findings):
    val = key_value(args, "value")
    if val and re.match(r"^['\"][\d.,\s]+['\"]$", val):
        findings.append(Finding(
            path, line_of(text, offset), "ERROR",
            f"value: {val} -- must be a number, not a string. A quoted or comma-decimal value "
            "is accepted and then ignored by optimization.",
        ))

    cur = key_value(args, "currency")
    if cur:
        m = re.match(r"^['\"](.+)['\"]$", cur)
        if m and not re.match(r"^[A-Za-z]{3}$", m.group(1)):
            findings.append(Finding(
                path, line_of(text, offset), "ERROR",
                f"currency: {cur} -- must be a 3-letter ISO 4217 code (e.g. 'USD'), not a symbol.",
            ))

    ids = key_value(args, "content_ids")
    if ids and re.match(r"^\[", ids):
        if re.search(r"[\[,]\s*\d+(\.\d+)?\s*[,\]]", ids):
            findings.append(Finding(
                path, line_of(text, offset), "ERROR",
                f"content_ids: {ids[:44]} contains numeric literals. Catalog matching is "
                "type-sensitive -- [1234] does not match '1234'. Wrap every id in String().",
            ))

    if has_key(args, "num_items"):
        ev = key_value(args, "event") or key_value(args, "event_name") or ""
        if ev and not re.search(r"InitiateCheckout|begin_checkout", ev, re.I):
            findings.append(Finding(
                path, line_of(text, offset), "WARN",
                f"num_items is set on {ev.strip()} -- Meta reads num_items on InitiateCheckout "
                "only. Elsewhere it is ignored.",
            ))


def check_ga4_event_name(path, text, offset, args, findings):
    ev = key_value(args, "event")
    if not ev:
        return
    m = re.match(r"^['\"]([^'\"]+)['\"]$", ev)
    if not m:
        return
    name = m.group(1)
    if name.startswith("gtm."):
        return
    if len(name) > 40:
        findings.append(Finding(
            path, line_of(text, offset), "ERROR",
            f"event name '{name}' is {len(name)} chars -- GA4 caps event names at 40 and "
            "truncates silently.",
        ))
    elif not GA4_EVENT_NAME_OK.match(name):
        findings.append(Finding(
            path, line_of(text, offset), "WARN",
            f"event name '{name}' -- GA4 event names must be letters/numbers/underscores and "
            "start with a letter. Spaces and dashes are dropped or mangled.",
        ))


def check_capi_payload(path, text, findings):
    """Server-side CAPI event objects: user_data must be pre-hashed, fbp/fbc must not be."""
    for m in re.finditer(r"event_name\s*:", text):
        window = text[m.start():m.start() + 2600]
        if "user_data" not in window:
            continue

        # The same shape rules apply on the server, where nothing validates them either.
        check_event_id(path, text, m.start(), window, findings, "a CAPI event")
        check_hashing(path, text, m.start(), window, findings, in_datalayer=False)
        check_ecommerce_shape(path, text, m.start(), window, findings)

        ud = key_value(window, "user_data")
        if not ud:
            continue
        check_hashing(path, text, m.start(), ud, findings, in_datalayer=False)
        for field in ("em", "ph", "fn", "ln", "ct", "st", "zp", "country", "db", "ge"):
            val = key_value(ud, field)
            if not val:
                continue
            if HASH_CALL.search(val) or HEX64.search(val):
                continue
            if EMAILISH.search(val) or re.search(r"\.(email|phone|firstName|lastName)\b", val):
                findings.append(Finding(
                    path, line_of(text, m.start()), "ERROR",
                    f"CAPI user_data.{field} = {val.strip()[:40]} appears to be plaintext. "
                    "The server side must send SHA-256 hex, normalized first (trim/lowercase; "
                    "phone digits-only with country code). Un-normalized hashes match nobody.",
                ))
                break

    if re.search(r"['\"]?test_event_code['\"]?\s*[:=]", text):
        m = re.search(r"['\"]?test_event_code['\"]?\s*[:=]", text)
        findings.append(Finding(
            path, line_of(text, m.start()), "WARN",
            "test_event_code is present -- events carrying it do not count toward optimization. "
            "Confirm it is environment-gated and cannot reach production.",
        ))


def check_consent_order(path, text, findings):
    if not re.search(r"googletagmanager\.com/gtm\.js|GTM-[A-Z0-9]{4,}", text):
        return
    gtm = re.search(r"googletagmanager\.com/gtm\.js|\(window,document,['\"]script['\"],"
                    r"['\"]dataLayer['\"]", text)
    consent = re.search(r"['\"]consent['\"]\s*,\s*['\"]default['\"]", text)
    if gtm and not consent:
        return  # consent default may legitimately live in another file
    if gtm and consent and consent.start() > gtm.start():
        findings.append(Finding(
            path, line_of(text, consent.start()), "ERROR",
            "gtag('consent','default',...) appears AFTER the GTM snippet. Tags that fire before "
            "the default is set have already fired -- there is no undo, and nothing warns you. "
            "Move the consent default above the container snippet.",
        ))


def check_file(path):
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [Finding(str(path), 0, "WARN", f"could not read: {exc}")]

    p = str(path)
    pushes = list(iter_calls(text, r"\bdataLayer\s*\.\s*push\s*\("))

    for idx, (offset, args) in enumerate(pushes):
        check_event_id(p, text, offset, args, findings, "a dataLayer push")
        check_hashing(p, text, offset, args, findings, in_datalayer=True)
        check_ecommerce_shape(p, text, offset, args, findings)
        check_ga4_event_name(p, text, offset, args, findings)

        if has_key(args, "ecommerce") and re.search(r"ecommerce\s*:\s*undefined", args):
            findings.append(Finding(
                p, line_of(text, offset), "ERROR",
                "ecommerce: undefined does not clear GTM's data model -- it merges, so the key "
                "persists. Use `dataLayer.push({ ecommerce: null })`.",
            ))

        # An ecommerce payload push must be preceded by a null-clearing push.
        is_clear = re.search(r"ecommerce\s*:\s*null", args) is not None
        carries_ecom = has_key(args, "ecommerce") and not is_clear
        if not carries_ecom:
            continue
        ev = key_value(args, "event") or ""
        evm = re.match(r"^['\"]([^'\"]+)['\"]$", ev.strip()) if ev else None
        if evm and evm.group(1) not in ECOMMERCE_EVENTS:
            continue

        prev_clear = False
        if idx > 0 and re.search(r"ecommerce\s*:\s*null", pushes[idx - 1][1]):
            prev_clear = True
        if not prev_clear:
            back = text[max(0, offset - 600):offset]
            if re.search(r"ecommerce\s*:\s*null", back):
                prev_clear = True
        if not prev_clear:
            findings.append(Finding(
                p, line_of(text, offset), "ERROR",
                "ecommerce push with no preceding `dataLayer.push({ ecommerce: null })`. GTM's "
                "model MERGES rather than replaces, so the previous event's items[] bleed into "
                "this one. The totals stay plausible, which is why nobody notices.",
            ))

    # String() discipline on item_id -> content_ids mappings.
    for m in re.finditer(r"content_ids[^;\n]{0,120}?\.map\s*\(([^;]{0,160})", text):
        body = m.group(1)
        if "item_id" in body and "String(" not in body:
            findings.append(Finding(
                p, line_of(text, m.start()), "WARN",
                "content_ids mapped from item_id without String(). If any SKU is numeric the "
                "catalog join fails silently. Normalizing contents[].id but not content_ids is "
                "the usual half-fix.",
            ))

    for offset, args in iter_calls(text, r"\bfbq\s*\(\s*['\"]track"):
        check_event_id(p, text, offset, args, findings, "an fbq() call")

    check_capi_payload(p, text, findings)
    check_consent_order(p, text, findings)
    return findings


def collect(paths):
    out = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and f.suffix.lower() in SOURCE_SUFFIXES:
                    if not any(part in SKIP_DIRS for part in f.parts):
                        out.append(f)
        else:
            print(f"warning: no such file or directory: {raw}", file=sys.stderr)
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    files = collect(argv[1:])
    if not files:
        print("No source files found to check.", file=sys.stderr)
        return 2

    findings = []
    for f in files:
        findings.extend(check_file(f))

    # Overlapping scan windows can surface the same issue twice.
    seen, unique = set(), []
    for f in findings:
        key = (f.path, f.line, f.message)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    findings = unique

    errors = [f for f in findings if f.level == "ERROR"]
    warns = [f for f in findings if f.level == "WARN"]

    for f in sorted(findings, key=lambda x: (x.path, x.line)):
        print(f)

    print(
        f"\n{len(files)} file(s) checked -- {len(errors)} error(s), {len(warns)} warning(s).",
        file=sys.stderr,
    )
    if not findings:
        print(
            "Static checks pass. This does NOT mean events fire: confirm in GTM Preview, GA4 "
            "DebugView, and Meta Test Events -- and confirm dedup shows '1 event from 2 sources'.",
            file=sys.stderr,
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
