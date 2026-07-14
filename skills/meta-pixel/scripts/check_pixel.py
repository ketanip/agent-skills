#!/usr/bin/env python3
"""Lint Meta Pixel (fbq) calls for the malformed-parameter patterns that fail silently.

Usage:
    python check_pixel.py <file-or-dir> [<file-or-dir> ...]

Exit codes: 0 = clean, 1 = errors found, 2 = bad invocation.

Catches what Meta's docs call out as the recurring mistakes: value as a string,
currency as a symbol, content_ids as a comma-string, contents entries missing
quantity, content_type that isn't 'product', Purchase without value/currency,
non-standard event names sent through track(), and plain track() on pages that
initialize more than one pixel (which over-fires to every pixel).

This is a static linter over source text. It cannot tell you whether an event
actually fires in the browser -- always confirm with the Pixel Helper.
"""

import re
import sys
from pathlib import Path

STANDARD_EVENTS = {
    "AddPaymentInfo", "AddToCart", "AddToWishlist", "CompleteRegistration",
    "Contact", "CustomizeProduct", "Donate", "FindLocation", "InitiateCheckout",
    "Lead", "PageView", "Purchase", "Schedule", "Search", "StartTrial",
    "SubmitApplication", "Subscribe", "ViewContent",
}

SOURCE_SUFFIXES = {
    ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".vue", ".svelte",
    ".php", ".erb", ".liquid", ".hbs", ".ejs", ".astro", ".mdx",
}

SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "vendor", "__pycache__"}

ISO_CURRENCY = re.compile(r"^[A-Za-z]{3}$")


class Finding:
    def __init__(self, path, line, level, message):
        self.path, self.line, self.level, self.message = path, line, level, message


def iter_fbq_calls(text):
    """Yield (start_offset, args_source) for each fbq(...) call, paren-balanced."""
    for m in re.finditer(r"\bfbq\s*\(", text):
        depth, i, n = 0, m.end() - 1, len(text)
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
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    yield m.start(), text[m.end():i]
                    break
            i += 1


def split_args(src):
    """Split a call's argument source on top-level commas."""
    args, depth, cur = [], 0, []
    in_str, quote, esc = False, "", False
    for ch in src:
        if in_str:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in "\"'`":
            in_str, quote = True, ch
            cur.append(ch)
        elif ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        args.append("".join(cur).strip())
    return args


def unquote(arg):
    arg = arg.strip()
    if len(arg) >= 2 and arg[0] in "\"'`" and arg[-1] == arg[0]:
        return arg[1:-1]
    return None


def prop(obj_src, key):
    """Crude value lookup for `key` in an object literal. Returns raw source or None."""
    m = re.search(rf"""["']?\b{key}\b["']?\s*:\s*""", obj_src)
    if not m:
        return None
    i, depth, out = m.end(), 0, []
    in_str, quote, esc = False, "", False
    while i < len(obj_src):
        ch = obj_src[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        elif ch in "\"'`":
            in_str, quote = True, ch
            out.append(ch)
        elif ch in "([{":
            depth += 1
            out.append(ch)
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
            out.append(ch)
        elif ch == "," and depth == 0:
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out).strip()


def check_params(obj_src, event, path, line, out):
    def err(msg):
        out.append(Finding(path, line, "error", msg))

    def warn(msg):
        out.append(Finding(path, line, "warn", msg))

    currency = prop(obj_src, "currency")
    if currency is not None:
        lit = unquote(currency)
        if lit is not None and not ISO_CURRENCY.match(lit):
            err(f"currency: {currency} — must be a 3-letter ISO 4217 code (e.g. 'USD'), not a symbol")

    value = prop(obj_src, "value")
    if value is not None:
        lit = unquote(value)
        if lit is not None:
            err(f"value: {value} — must be a number, not a string (a comma decimal like '5000,00' is dropped)")

    content_type = prop(obj_src, "content_type")
    if content_type is not None:
        lit = unquote(content_type)
        if lit is not None and lit not in ("product", "product_group"):
            err(f"content_type: {content_type} — must be 'product' or 'product_group'")

    content_ids = prop(obj_src, "content_ids")
    if content_ids is not None:
        if not content_ids.startswith("["):
            lit = unquote(content_ids)
            if lit is not None:
                err(f"content_ids: {content_ids} — must be an array, e.g. ['{lit.split(',')[0]}']")
        elif content_ids.replace(" ", "") == "[]":
            err("content_ids: [] — empty array carries no product IDs")

    contents = prop(obj_src, "contents")
    if contents is not None and contents.startswith("["):
        for entry in re.findall(r"\{[^{}]*\}", contents):
            if re.search(r"""["']?\bid\b["']?\s*:""", entry) and not re.search(
                r"""["']?\bquantity\b["']?\s*:""", entry
            ):
                err(f"contents entry {entry.strip()} is missing the required `quantity` key")

    if event == "Purchase":
        if value is None:
            err("Purchase is missing the required `value` parameter")
        if currency is None:
            err("Purchase is missing the required `currency` parameter")

    if event in ("AddToCart", "Purchase", "ViewContent") and content_ids is None and contents is None:
        warn(
            f"{event} has neither `content_ids` nor `contents` — required for "
            "Advantage+ catalog ads and Collaborative Ads"
        )


def check_file(path, out):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        out.append(Finding(path, 1, "error", f"could not read: {e}"))
        return

    if "fbq" not in text:
        return

    calls = list(iter_fbq_calls(text))
    init_ids, tracks = set(), []

    for offset, arg_src in calls:
        line = text.count("\n", 0, offset) + 1
        args = split_args(arg_src)
        if not args:
            continue
        method = unquote(args[0])
        if method is None:
            continue

        if method == "init" and len(args) >= 2:
            pid = unquote(args[1])
            init_ids.add(pid if pid is not None else args[1])

        elif method in ("track", "trackCustom", "trackSingle", "trackSingleCustom"):
            single = method.startswith("trackSingle")
            name_idx = 2 if single else 1
            if len(args) <= name_idx:
                continue
            event = unquote(args[name_idx])
            params = args[name_idx + 1] if len(args) > name_idx + 1 else None
            tracks.append((line, method, event, single))

            if method == "track" and event and event not in STANDARD_EVENTS:
                out.append(
                    Finding(
                        path, line, "error",
                        f"'{event}' is not a standard event — use "
                        f"fbq('trackCustom', '{event}', ...) instead",
                    )
                )
            if params and params.lstrip().startswith("{") and event:
                check_params(params, event, path, line, out)

    if len(init_ids) > 1:
        for line, method, event, single in tracks:
            if not single and event != "PageView":
                out.append(
                    Finding(
                        path, line, "error",
                        f"{len(init_ids)} pixels are initialized in this file, so "
                        f"fbq('{method}', '{event}') fires on ALL of them — use "
                        f"'{'trackSingle' if method == 'track' else 'trackSingleCustom'}' "
                        "with an explicit pixel ID",
                    )
                )

    if tracks and not init_ids and "fbevents.js" not in text:
        out.append(
            Finding(
                path, tracks[0][0], "warn",
                "events are tracked here but no fbq('init') / base code in this file — "
                "confirm the base code loads on every page that tracks",
            )
        )


def collect(paths):
    files = []
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            for f in p.rglob("*"):
                if (
                    f.is_file()
                    and f.suffix.lower() in SOURCE_SUFFIXES
                    and not any(part in SKIP_DIRS for part in f.parts)
                ):
                    files.append(f)
        else:
            print(f"warning: {raw} does not exist", file=sys.stderr)
    return files


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2

    findings = []
    files = collect(argv[1:])
    for f in files:
        check_file(f, findings)

    errors = [f for f in findings if f.level == "error"]
    warns = [f for f in findings if f.level == "warn"]

    for f in sorted(findings, key=lambda f: (str(f.path), f.line)):
        tag = "ERROR" if f.level == "error" else "warn "
        print(f"{tag} {f.path}:{f.line}: {f.message}")

    print(
        f"\nScanned {len(files)} file(s): {len(errors)} error(s), {len(warns)} warning(s)."
    )
    if not findings:
        print("No malformed fbq() parameters found. Still verify with the Pixel Helper —")
        print("this linter cannot tell you whether the events actually fire.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
