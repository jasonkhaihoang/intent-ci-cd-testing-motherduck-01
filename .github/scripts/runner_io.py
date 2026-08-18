"""GitHub Actions runner protocol seam.

One module that owns every write to the runner's output, env, and log
directive channels. CI scripts must route runner directives through here
instead of writing bare `::warning::` strings or appending to
`$GITHUB_OUTPUT` / `$GITHUB_ENV` directly.

Public surface:
  set_output(key, value)
  set_env(key, value)
  set_env_multiline(key, value, delimiter="EOF_RUNNER_IO")
  mask(value)
  warning(msg)
  error(msg)
  notice(msg)

When `GITHUB_OUTPUT` / `GITHUB_ENV` are unset (e.g. local runs), values
are printed instead so contributors still see what would be emitted.
"""

import os
import sys

_DEFAULT_DELIMITER = "EOF_RUNNER_IO"


def set_output(key: str, value: str) -> None:
    """Append a step output to $GITHUB_OUTPUT, or print when unset."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"{key}={value}\n")
    else:
        print(f"GITHUB_OUTPUT not set; {key}={value}", flush=True)


def set_env(key: str, value: str) -> None:
    """Append a key=value pair to $GITHUB_ENV, or print when unset."""
    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a") as f:
            f.write(f"{key}={value}\n")
    else:
        print(f"GITHUB_ENV not set; {key}={value}", flush=True)


def set_env_multiline(key: str, value: str, delimiter: str = _DEFAULT_DELIMITER) -> None:
    """Write a multiline value to $GITHUB_ENV using heredoc syntax."""
    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a") as f:
            f.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")
    else:
        print(f"GITHUB_ENV not set; {key}=<multiline>", flush=True)


def mask(value: str) -> None:
    """Instruct the runner to redact `value` from all log output."""
    print(f"::add-mask::{value}", flush=True)


def warning(msg: str) -> None:
    print(f"::warning::{msg}", flush=True)


def error(msg: str) -> None:
    print(f"::error::{msg}", file=sys.stderr, flush=True)


def notice(msg: str) -> None:
    print(f"::notice::{msg}", flush=True)
