"""Deep module for the domain-repo pre-push hook.

Public thin interfaces:
    evaluate_publish(entries) -> dict
    render_block_message(findings) -> str

Pure: no I/O, no subprocess, no filesystem access. The shell
(domain_repo_pre_hook_runner.py) gathers git state and calls these.

The classification/secret helpers below (_classify_path, _is_secret_filename,
_scan_secret_content) are internal — they have no call site outside
evaluate_publish and are deliberately not exported or tested directly (this
repo's doctrine: test the thin interface, not decomposed internals).

Design contracts (docs/design/domain-repo-pre-hook/README.md):
    DC-1  _classify_path           — path-anchored artifact-class recognition.
                                     Dependency-manager directories (vendored
                                     packages) are matched at any depth, since
                                     a real install legitimately nests there;
                                     build/runtime/database classes are
                                     anchored to a project root or one level
                                     under it.
    DC-2  _is_secret_filename      — conventional secret-holding filenames
    DC-3  _scan_secret_content     — secret-shaped content, independent of filename
                                     (VD-4622 extended this with context-independent
                                     GitHub/Slack/Stripe/Google/JWT patterns and a
                                     bearer-token header pattern; see D5a)
    DC-4  evaluate_publish         — block iff any finding exists
    DC-5  evaluate_publish         — remediation text selection per finding type
    DC-6  evaluate_publish         — a positive finding is never suppressed by
                                     unrelated input incompleteness, and each
                                     finding type is evaluated independently
                                     per path (an artifact-classified or
                                     force-added-ignored path is still checked
                                     for secret content)
"""
from __future__ import annotations

import re

_VENDORED_PACKAGE_RE = re.compile(r"(^|/)(dbt_packages|node_modules|\.venv|venv)/")
_BUILD_ARTIFACT_RE = re.compile(
    r"(^|/)(__pycache__|\.agents_tmp|\.pytest_cache|\.ruff_cache|\.mypy_cache)/"
    r"|^([^/]+/)?target/"
    r"|\.pyc$"
)
_RUNTIME_OUTPUT_RE = re.compile(r"^([^/]+/)?logs/|\.log$")
_DATABASE_FILE_RE = re.compile(r"\.duckdb(\.wal)?$")

# DC-2 — conventional secret-holding filenames. .env's env-suffixed variants
# (.env.local, .env.production, ...) are common and included explicitly.
# Placeholder-file suffixes (.example, .sample, .template, .dist, .defaults)
# are excluded: these are conventionally committed with no real values, and
# the DC-3 content scan still catches an actual secret pasted into one.
_SECRET_FILENAME_RE = re.compile(
    r"(^|/)(\.env(\.(?!example$|sample$|template$|dist$|defaults$)[A-Za-z0-9_-]+)?"
    r"|secrets\.toml|\.user\.yml"
    r"|id_rsa|id_dsa|id_ecdsa|id_ed25519)$"
)

# DC-3 — secret-shaped content, independent of filename. Quotes are optional:
# a mandatory-quotes pattern misses the most common unquoted `.env`-style
# `KEY=value` leak shape.
#
# Why 16 chars (the generic key/secret/token/password rule's value-length
# floor): every current major provider's real secret body is far longer —
# AWS Secret Access Key 40, GitHub PAT 36 (classic) / ~82 (fine-grained),
# Slack up to 34, Stripe 32, OpenAI 48-155, Anthropic ~100, JWT 100+ — so 16
# is not the limiting factor for catching any documented real-world format;
# it exists only to reject obviously-too-short values (small IDs, version
# strings, enum-like assignments) before the keyword+digit check runs. This
# mirrors how gitleaks/TruffleHog/detect-secrets treat length: never the sole
# gate, always paired with another signal (their entropy check; here, the
# keyword prefix + "contains a digit" requirement) — 16 was picked, not
# derived, and sits within the 10-20 char range those tools use for the same
# purpose. Per D5 (docs/design/domain-repo-pre-hook/README.md), this hook is
# intentionally the fast/shallow local layer, not entropy-scored like
# gitleaks — `ci/static-check`'s gitleaks scan is the deeper backstop.
_SECRET_CONTENT_PATTERNS = [
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(
        rb"(?i)([a-z0-9]+_)?(api[_-]?key|secret|token|password)(_[a-z0-9]+)*\s*[=:]\s*"
        rb"['\"]?(?=[A-Za-z0-9_\-/+]{16,})[A-Za-z0-9_\-/+]*[0-9][A-Za-z0-9_\-/+]*['\"]?"
    ),
]

# VD-4622 (D5a) — context-independent vendor-shaped patterns: matched on the
# value's own shape alone, no keyword neighbor required, the same way AKIA and
# the PEM header above already work. Realizes AC-DRPH-39..43.
_VENDOR_SECRET_PATTERNS = [
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{36}"),  # AC-DRPH-39 — GitHub PAT
    re.compile(rb"xox[baprs]-[0-9]+-[0-9]+-[A-Za-z0-9]+"),  # AC-DRPH-40 — Slack token
    re.compile(rb"(sk|pk|rk)_(live|test)_[A-Za-z0-9]{24,}"),  # AC-DRPH-41 — Stripe key
    re.compile(rb"AIza[0-9A-Za-z_\-]{35}"),  # AC-DRPH-42 — Google API key
    re.compile(rb"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # AC-DRPH-43 — JWT
]

# VD-4622 (D5a) — bearer-token header shape has no vendor-specific charset of
# its own, so it is the one new pattern that needs its own placeholder guard:
# a value that looks like a documentation placeholder (all-caps/underscore,
# or containing `<`, `>`, or a repeated-`x` run) is excluded. Realizes
# AC-DRPH-44 (required-output) and AC-DRPH-45 (forbidden-state guard).
_BEARER_TOKEN_RE = re.compile(rb"Bearer\s+([A-Za-z0-9_\-.]{20,})")
# Literal all-caps/digits/underscore/hyphen (no lowercase) — a real opaque
# token is virtually never shaped this way, but "YOUR_TOKEN_HERE" and
# "YOUR-TOKEN-HERE" both are. Kept case-SENSITIVE deliberately: matching
# case-insensitively would also match ordinary lowercase alphanumeric
# tokens, defeating the guard entirely.
_BEARER_ALL_CAPS_PLACEHOLDER_RE = re.compile(rb"^[A-Z0-9_\-]+$")
# Accepted residual false-negative (not fixed): a real token containing 4+
# consecutive x/X characters (plausible in base64/hex) is also exempted by
# this marker check. Low-probability, same spirit as ADR 0020's other
# accepted-risk trade-offs for this pattern set.
_BEARER_MARKER_PLACEHOLDER_RE = re.compile(rb"[<>]|[xX]{4,}")

_ARTIFACT_REMEDIATION = (
    "Add the missing pattern to .gitignore, then `git rm -r --cached <path>` and commit."
)
_SECRET_UNTRACK_REMEDIATION = (
    "Remove the secret from the file (or delete the file) and `git rm --cached <path>` "
    "before committing — this secret has not yet reached history."
)
_SECRET_ROTATE_REMEDIATION = (
    "Untracking is not enough — this secret is already in history. Rotate the exposed "
    "credential and report the exposure, then remove it from the file going forward."
)


def _classify_path(path: str) -> str | None:
    if _VENDORED_PACKAGE_RE.search(path):
        return "vendored-package"
    if _BUILD_ARTIFACT_RE.search(path):
        return "build-artifact"
    if _RUNTIME_OUTPUT_RE.search(path):
        return "runtime-output"
    if _DATABASE_FILE_RE.search(path):
        return "database-file"
    return None


def _is_secret_filename(path: str) -> bool:
    return bool(_SECRET_FILENAME_RE.search(path))


def _is_bearer_token_placeholder(value: bytes) -> bool:
    return bool(_BEARER_ALL_CAPS_PLACEHOLDER_RE.match(value) or _BEARER_MARKER_PLACEHOLDER_RE.search(value))


def _scan_secret_content(content: bytes) -> bool:
    if any(pattern.search(content) for pattern in _SECRET_CONTENT_PATTERNS):
        return True
    if any(pattern.search(content) for pattern in _VENDOR_SECRET_PATTERNS):
        return True
    bearer_match = _BEARER_TOKEN_RE.search(content)
    if bearer_match and not _is_bearer_token_placeholder(bearer_match.group(1)):
        return True
    return False


def evaluate_publish(entries: list[dict]) -> dict:
    """DC-4/DC-5/DC-6: decide allow/block for a publish attempt's changed files."""
    findings = []
    for entry in entries:
        path = entry["path"]

        artifact_class = _classify_path(path)
        if artifact_class is not None:
            findings.append({"path": path, "class": artifact_class, "remediation": _ARTIFACT_REMEDIATION})

        if entry.get("force_added_ignored"):
            findings.append({"path": path, "class": "force-added-ignored", "remediation": _ARTIFACT_REMEDIATION})

        content = entry.get("content")
        is_secret = _is_secret_filename(path) or (content is not None and _scan_secret_content(content))
        if is_secret:
            remediation = _SECRET_ROTATE_REMEDIATION if entry.get("in_history") else _SECRET_UNTRACK_REMEDIATION
            findings.append({"path": path, "class": "secret", "remediation": remediation})

    decision = "block" if findings else "allow"
    return {"decision": decision, "findings": findings}


def render_block_message(findings: list[dict]) -> str:
    """Pure formatting. Exposed here (not in the shell) because it is pure and
    has a real caller outside this module (domain_repo_pre_hook_runner.main)."""
    lines = [f"BLOCKED: this branch carries {len(findings)} disqualifying finding(s)."]
    for finding in findings:
        lines.append(f"  {finding['path']} ({finding['class']}): {finding['remediation']}")
    return "\n".join(lines)
