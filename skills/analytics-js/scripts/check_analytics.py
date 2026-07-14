#!/usr/bin/env python3
"""Lint analytics-js (getanalytics.io) setups for the mistakes that fail silently.

Usage:
    python check_analytics.py <file-or-dir> [<file-or-dir> ...]

Exit codes: 0 = clean (or warnings only), 1 = errors found, 2 = bad invocation.

analytics-js never throws at you. A plugin registered without being invoked, an
`abort()` that isn't returned, an enricher listed after the provider it meant to
enrich, a script-loading plugin with no `loaded()` -- every one of these leaves
you with code that looks correct and events that never arrive. This catches the
ones that are visible in source text.

It is a static linter. It cannot tell you an event actually fired. Confirm that
with debug:true + Redux DevTools and the destination's own dashboard.
"""

import re
import sys
from pathlib import Path

SOURCE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".astro"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".nuxt", "coverage", "__pycache__"}

# Lifecycle events a plugin may hook. Source: analytics-core/src/events.js
CORE_EVENTS = {
    "bootstrap", "params", "campaign",
    "initializeStart", "initialize", "initializeEnd", "ready",
    "pageStart", "page", "pageEnd", "pageAborted",
    "trackStart", "track", "trackEnd", "trackAborted",
    "identifyStart", "identify", "identifyEnd", "identifyAborted", "userIdChanged",
    "setItemStart", "setItem", "setItemEnd", "setItemAborted",
    "removeItemStart", "removeItem", "removeItemEnd", "removeItemAborted",
    "online", "offline",
    "resetStart", "reset", "resetEnd",
    "registerPlugins", "enablePlugin", "disablePlugin",
}
# Non-event keys that are legal on a plugin object.
PLUGIN_META_KEYS = {"name", "config", "EVENTS", "methods", "loaded", "enabled"}

# Hooks that receive `abort` and can cancel a call.
ABORTABLE_HOOKS = {"initializeStart", "pageStart", "trackStart", "identifyStart",
                   "setItemStart", "removeItemStart"}

# Packages whose default export is a FACTORY and must be invoked in the plugins array.
# Deliberately a known-good list: some community plugins (e.g. analytics-plugin-tab-events)
# export a plain plugin object and are correctly registered uninvoked, so we cannot infer
# this from the package name alone without flagging correct code.
FACTORY_PACKAGES = {
    "@analytics/google-analytics", "@analytics/google-analytics-v3",
    "@analytics/google-tag-manager", "@analytics/segment", "@analytics/mixpanel",
    "@analytics/amplitude", "@analytics/customerio", "@analytics/hubspot",
    "@analytics/fullstory", "@analytics/intercom", "@analytics/snowplow",
    "@analytics/crazy-egg", "@analytics/perfumejs", "@analytics/simple-analytics",
    "@analytics/aws-pinpoint", "@analytics/countly", "@analytics/gosquared",
    "@analytics/ownstats", "@analytics/original-source",
    "analytics-plugin-do-not-track", "analytics-plugin-event-validation",
    "analytics-plugin-original-source",
}

# Markers that a plugin's initialize() injects a third-party script.
SCRIPT_INJECTION = re.compile(
    r"createElement\s*\(\s*['\"]script['\"]|appendChild|insertBefore|\.src\s*=|loadScript|injectScript"
)


class Finding:
    __slots__ = ("path", "line", "level", "message")

    def __init__(self, path, line, level, message):
        self.path, self.line, self.level, self.message = path, line, level, message


def strip_noise(text):
    """Blank out comments and string bodies so scanning can't trip on them.

    Keeps offsets and newlines identical to the original, so line numbers survive.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
        elif ch == "/" and nxt == "*":
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            for j in range(i, min(i + 2, n)):
                out[j] = " "
            i += 2
        elif ch in "\"'`":
            quote = ch
            i += 1
            while i < n:
                if text[i] == "\\":
                    out[i] = " "
                    if i + 1 < n:
                        out[i + 1] = " "
                    i += 2
                    continue
                if text[i] == quote:
                    break
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            i += 1
        else:
            i += 1
    return "".join(out)


def match_bracket(text, open_idx):
    """Return the index of the bracket closing the one at open_idx, or -1."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    opener = text[open_idx]
    closer = pairs[opener]
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return i
    return -1


def split_top_level(src):
    """Split on commas that sit at bracket depth zero."""
    parts, depth, current = [], 0, []
    for ch in src:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if "".join(current).strip():
        parts.append("".join(current))
    return parts


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def object_keys(obj_src):
    """Top-level keys of an object literal body. Returns {key: offset_in_obj_src}."""
    keys, depth = {}, 0
    for m in re.finditer(r"""(?:(['"])([^'"]+)\1|([A-Za-z_$][\w$]*))\s*:""", obj_src):
        prefix = obj_src[: m.start()]
        depth = prefix.count("{") + prefix.count("[") + prefix.count("(") \
            - prefix.count("}") - prefix.count("]") - prefix.count(")")
        if depth == 0:
            keys[m.group(2) or m.group(3)] = m.start()
    # shorthand methods: `myHook({ payload }) {`
    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", obj_src):
        prefix = obj_src[: m.start()]
        depth = prefix.count("{") + prefix.count("[") - prefix.count("}") - prefix.count("]")
        if depth == 0 and m.group(1) not in ("if", "for", "while", "switch", "catch", "function"):
            keys.setdefault(m.group(1), m.start())
    return keys


def package_to_plugin_name(pkg):
    """'@analytics/google-analytics' -> 'google-analytics'; 'analytics-plugin-x' -> 'x'."""
    if pkg.startswith("@analytics/"):
        return pkg.split("/", 1)[1]
    if pkg.startswith("analytics-plugin-"):
        return pkg[len("analytics-plugin-"):]
    return None


def collect_imports(text):
    """identifier -> package, for analytics plugin packages."""
    imports = {}
    for m in re.finditer(r"""import\s+([A-Za-z_$][\w$]*)\s+from\s+['"]([^'"]+)['"]""", text):
        imports[m.group(1)] = m.group(2)
    for m in re.finditer(
        r"""(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*require\s*\(\s*['"]([^'"]+)['"]\s*\)""", text
    ):
        imports[m.group(1)] = m.group(2)
    return imports


def resolve_object_body(text, ident):
    """Body of `const ident = {...}`, or of the object returned by `function ident()`."""
    m = re.search(r"(?:const|let|var)\s+" + re.escape(ident) + r"\s*=\s*\{", text)
    if m:
        open_idx = text.index("{", m.end() - 1)
        close = match_bracket(text, open_idx)
        if close != -1:
            return text[open_idx + 1:close], open_idx
    m = re.search(r"function\s+" + re.escape(ident) + r"\s*\(", text)
    if not m:
        m = re.search(r"(?:const|let|var)\s+" + re.escape(ident) + r"\s*=\s*(?:function|\()", text)
    if m:
        ret = re.search(r"return\s*\{", text[m.end():])
        if ret:
            open_idx = m.end() + ret.end() - 1
            close = match_bracket(text, open_idx)
            if close != -1:
                return text[open_idx + 1:close], open_idx
    return None, None


class PluginEntry:
    def __init__(self, name, index, offset, body, source_pkg):
        self.name = name          # plugin `name` (namespace), if known
        self.index = index        # position in the plugins array
        self.offset = offset      # offset in file, for line numbers
        self.body = body          # object literal body, if resolvable
        self.source_pkg = source_pkg


def check_file(path, findings):
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = strip_noise(raw)

    def add(level, idx, msg):
        findings.append(Finding(path, line_of(raw, idx), level, msg))

    imports = collect_imports(raw)

    # ---- abort() must be returned -------------------------------------------
    for m in re.finditer(r"\babort\s*\(", text):
        before = text[:m.start()].rstrip()
        if before.endswith("return") or before.endswith("=>") or before.endswith("("):
            continue
        # `const x = abort(...)` / `await abort(...)` are still not returned, but
        # bare `abort('reason')` as a statement is the classic silent no-op.
        if re.search(r"[=:]\s*$", before):
            continue
        add("ERROR", m.start(),
            "abort() is called but not returned -- the call is NOT cancelled. "
            "Use `return abort('reason')`.")

    # ---- Analytics({...}) config --------------------------------------------
    analytics_calls = list(re.finditer(r"\bAnalytics\s*\(", text))
    if not analytics_calls:
        analytics_calls = list(re.finditer(r"_analytics\s*\.\s*init\s*\(", text))

    for call in analytics_calls:
        open_idx = text.index("(", call.end() - 1)
        close = match_bracket(text, open_idx)
        if close == -1:
            continue
        # The config object literal, unwrapped from its outer braces -- object_keys()
        # measures bracket depth, so it needs the body, not the whole literal.
        args_src = text[open_idx + 1:close]
        brace = args_src.find("{")
        if brace == -1:
            continue
        brace_close = match_bracket(args_src, brace)
        if brace_close == -1:
            continue
        cfg = args_src[brace + 1:brace_close]
        cfg_base = open_idx + 1 + brace + 1

        keys = object_keys(cfg)
        if "plugins" not in keys:
            continue

        arr_start = cfg.find("[", keys["plugins"])
        if arr_start == -1:
            continue
        arr_end = match_bracket(cfg, arr_start)
        if arr_end == -1:
            continue
        arr_src = cfg[arr_start + 1:arr_end]
        arr_base = cfg_base + arr_start + 1

        entries = []
        cursor = 0
        for i, chunk in enumerate(split_top_level(arr_src)):
            offset = arr_base + cursor + (len(chunk) - len(chunk.lstrip()))
            cursor += len(chunk) + 1
            entry_src = chunk.strip()
            if not entry_src or entry_src.startswith("..."):
                continue

            # invoked factory: pluginFn({...})
            fm = re.match(r"^([A-Za-z_$][\w$]*)\s*\(", entry_src)
            # bare identifier
            bm = re.match(r"^([A-Za-z_$][\w$]*)\s*$", entry_src)
            # inline object literal
            om = entry_src.startswith("{")

            if fm:
                ident = fm.group(1)
                pkg = imports.get(ident)
                name = package_to_plugin_name(pkg) if pkg else None
                body = None
                if not pkg:
                    body, _ = resolve_object_body(raw, ident)
                    if body:
                        name = plugin_name_of(body) or name
                args_open = entry_src.index("(", fm.end() - 1)
                args_close = match_bracket(entry_src, args_open)
                args = entry_src[args_open + 1:args_close] if args_close != -1 else ""
                check_provider_config(pkg, args, offset, add)
                entries.append(PluginEntry(name, i, offset, body, pkg))

            elif bm:
                ident = bm.group(1)
                pkg = imports.get(ident)
                if pkg and pkg in FACTORY_PACKAGES:
                    add("ERROR", offset,
                        f"`{ident}` is a plugin factory from '{pkg}' but is registered "
                        f"uninvoked -- it is a function, not a plugin object, so it is "
                        f"silently ignored. Call it: {ident}({{ ... }}).")
                    entries.append(PluginEntry(package_to_plugin_name(pkg), i, offset, None, pkg))
                    continue
                if pkg and package_to_plugin_name(pkg):
                    # A community plugin we don't know the shape of. Some export a plain
                    # object and are correctly registered bare -- don't guess.
                    entries.append(PluginEntry(package_to_plugin_name(pkg), i, offset, None, pkg))
                    continue
                body, body_off = resolve_object_body(raw, ident)
                if body is None:
                    entries.append(PluginEntry(None, i, offset, None, None))
                    continue
                name = check_plugin_object(body, body_off if body_off else offset, add)
                entries.append(PluginEntry(name, i, offset, body, None))

            elif om:
                close_obj = match_bracket(entry_src, 0)
                body = entry_src[1:close_obj] if close_obj != -1 else entry_src[1:]
                name = check_plugin_object(body, offset, add)
                entries.append(PluginEntry(name, i, offset, body, None))

        check_plugin_order(entries, add)

    # ---- .page(options) missing the empty first argument ---------------------
    for m in re.finditer(r"\.page\s*\(", text):
        open_idx = text.index("(", m.end() - 1)
        close = match_bracket(text, open_idx)
        if close == -1:
            continue
        args = split_top_level(text[open_idx + 1:close])
        if not args:
            continue
        first = args[0].strip()
        if first.startswith("{") and len(args) == 1:
            inner_close = match_bracket(first, 0)
            inner = first[1:inner_close] if inner_close != -1 else first[1:]
            if "plugins" in object_keys(inner):
                add("ERROR", m.start(),
                    "analytics.page({ plugins: ... }) -- the first argument is page DATA, "
                    "not options. Your plugin selector is being read as page data. "
                    "Use analytics.page({}, { plugins: ... }).")

    return findings


def plugin_name_of(body):
    m = re.search(r"""\bname\s*:\s*['"]([^'"]+)['"]""", body)
    return m.group(1) if m else None


def check_provider_config(pkg, args, offset, add):
    """Provider-specific config traps."""
    if pkg == "@analytics/google-analytics":
        if re.search(r"\btrackingId\b", args):
            add("ERROR", offset,
                "@analytics/google-analytics (GA4) takes `measurementIds: ['G-...']`, not "
                "`trackingId`. A GA4 plugin with no measurement ID silently sends nothing. "
                "For Universal Analytics use @analytics/google-analytics-v3.")
        elif not re.search(r"\bmeasurementIds\b", args):
            add("ERROR", offset,
                "@analytics/google-analytics requires `measurementIds` (an array of 'G-...' IDs).")
        elif re.search(r"measurementIds\s*:\s*['\"]", args):
            add("ERROR", offset, "`measurementIds` must be an ARRAY, even for a single ID.")
    if pkg == "@analytics/google-tag-manager" and not re.search(r"\bcontainerId\b", args):
        add("ERROR", offset, "@analytics/google-tag-manager requires `containerId`.")
    if pkg == "@analytics/segment" and not re.search(r"\bwriteKey\b", args):
        add("ERROR", offset, "@analytics/segment requires `writeKey`.")
    if pkg == "@analytics/mixpanel" and not re.search(r"\btoken\b", args):
        add("ERROR", offset, "@analytics/mixpanel requires `token`.")


def check_plugin_object(body, offset, add):
    """Validate a plugin object literal. Returns its `name`, if any."""
    keys = object_keys(body)
    name = plugin_name_of(body)

    hook_keys = [k for k in keys if k in CORE_EVENTS or ":" in k]
    if not name:
        if hook_keys or "methods" in keys:
            add("ERROR", offset,
                "Plugin object has no `name`. It is required -- `name` is the namespace that "
                "options.plugins, plugins.enable/disable, and `event:name` hooks all key off.")
        return None

    # A plugin that injects a script but never reports readiness.
    init_src = ""
    if "initialize" in keys:
        seg = body[keys["initialize"]:]
        brace = seg.find("{")
        if brace != -1:
            end = match_bracket(seg, brace)
            init_src = seg[brace:end] if end != -1 else seg[brace:]
    if init_src and SCRIPT_INJECTION.search(init_src) and "loaded" not in keys:
        add("ERROR", offset,
            f"Plugin '{name}' loads a third-party script in initialize() but has no `loaded()`. "
            "Without it, analytics doesn't know when the vendor global exists and the session's "
            "first events fire into a script tag that hasn't finished loading. They vanish "
            "silently. Add: loaded: () => !!window.someVendorGlobal")

    # Namespaced hooks must return the payload.
    for key, key_off in keys.items():
        if ":" not in key:
            continue
        seg = body[key_off:]
        arrow = seg.find("=>")
        if arrow == -1:
            continue
        # The body brace is the first `{` AFTER the arrow -- an earlier one is the
        # destructured parameter list, e.g. ({ payload }) => ...
        after = seg[arrow + 2:].lstrip()
        if not after.startswith("{"):
            continue  # concise arrow body -- it returns its expression implicitly
        body_open = seg.index("{", arrow + 2)
        end = match_bracket(seg, body_open)
        fn_body = seg[body_open:end] if end != -1 else ""
        if fn_body and not re.search(r"\breturn\b", fn_body):
            add("ERROR", offset,
                f"Namespaced hook '{key}' never returns a payload. Its return value is what "
                "that plugin receives -- mutating without returning discards your changes. "
                "`return Object.assign({}, payload, { properties })`")

    # Typo'd hook names are silently ignored by the library. Only flag near-misses of a
    # core event -- plugins legitimately emit their own custom events (tabHidden,
    # windowLeft, ...) for other plugins and listeners to hook, and those are not typos.
    for key in keys:
        if key in PLUGIN_META_KEYS or key in CORE_EVENTS or ":" in key:
            continue
        if not re.match(r"^[a-zA-Z][\w]*$", key):
            continue
        near = [e for e in CORE_EVENTS if edit_distance(key, e) <= 2]
        if near:
            add("WARN", offset,
                f"Plugin '{name}' has key `{key}`, which is not a lifecycle event but is one "
                f"character or two from `{sorted(near)[0]}`. Unrecognized hooks are ignored "
                "silently, so a typo here means the hook simply never runs.")
    return name


def edit_distance(a, b):
    """Levenshtein, used only to spot hook-name typos."""
    if abs(len(a) - len(b)) > 2:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def check_plugin_order(entries, add):
    """Enrichers/validators must precede the providers they modify or gate."""
    by_name = {e.name: e for e in entries if e.name}

    for e in entries:
        if not e.body:
            continue
        keys = object_keys(e.body)

        # Namespaced hook targeting a provider registered earlier in the array.
        for key in keys:
            if ":" not in key:
                continue
            target = key.split(":", 1)[1].strip()
            provider = by_name.get(target)
            if provider and provider.index < e.index:
                add("ERROR", e.offset,
                    f"Plugin '{e.name}' hooks '{key}' but is registered AFTER '{target}' in the "
                    "plugins array. The array is a pipeline -- an enricher listed after its "
                    "provider enriches nothing. Move it before.")

        # A validator/gate (aborts in a *Start hook) that sits after any provider.
        gates = [k for k in keys if k in ABORTABLE_HOOKS]
        if not gates:
            continue
        aborts = any(
            re.search(r"\babort\s*\(|\bthrow\b", e.body[keys[k]:keys[k] + 400]) for k in gates
        )
        if not aborts:
            continue
        providers_before = [p for p in entries if p.source_pkg and p.index < e.index]
        if providers_before:
            names = ", ".join(sorted({p.name or "?" for p in providers_before}))
            add("ERROR", e.offset,
                f"Validation/consent plugin '{e.name}' can abort calls but is registered after "
                f"provider plugin(s) ({names}). Gates must come first in the plugins array, or "
                "the providers they were meant to gate have already run.")


def iter_files(targets):
    for t in targets:
        p = Path(t)
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix in SOURCE_SUFFIXES \
                        and not any(part in SKIP_DIRS for part in f.parts):
                    yield f
        else:
            print(f"warning: no such file or directory: {t}", file=sys.stderr)


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2

    findings = []
    scanned = 0
    for f in iter_files(argv[1:]):
        scanned += 1
        try:
            check_file(f, findings)
        except Exception as exc:  # a linter that crashes is worse than one that misses
            print(f"warning: could not parse {f}: {exc}", file=sys.stderr)

    errors = [f for f in findings if f.level == "ERROR"]
    warns = [f for f in findings if f.level == "WARN"]

    for f in sorted(findings, key=lambda x: (str(x.path), x.line)):
        print(f"{f.level} {f.path}:{f.line}: {f.message}")

    if not findings:
        print(f"clean -- scanned {scanned} file(s), no issues found.")
    else:
        print(f"\n{len(errors)} error(s), {len(warns)} warning(s) across {scanned} file(s).")

    print("\nStatic analysis only: this cannot confirm an event actually fired. "
          "Verify with debug:true + Redux DevTools and the destination's dashboard.")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
