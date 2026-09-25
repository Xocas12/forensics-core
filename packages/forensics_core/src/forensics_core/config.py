"""Repository-level configuration: locate the repo root, read config/forensics.toml (with an
optional gitignored config/forensics.local.toml override), and expose the contact string,
User-Agent and per-host rate limits.

HARD RULE 6: network code must call :func:`require_contact` before any request. It raises
:class:`ContactNotConfigured` while the placeholder is still in place.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PLACEHOLDER_MARKER = "REPLACE_ME"
CONFIG_RELPATH = Path("config") / "forensics.toml"
LOCAL_CONFIG_RELPATH = Path("config") / "forensics.local.toml"


class ContactNotConfigured(RuntimeError):
    """Raised when config/forensics.toml still carries the placeholder contact string."""


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upwards from ``start`` (default: cwd, or $FORENSICS_ROOT) until a directory
    containing ``config/forensics.toml`` is found."""
    env = os.environ.get("FORENSICS_ROOT")
    if env:
        root = Path(env).resolve()
        if (root / CONFIG_RELPATH).exists():
            return root
        raise FileNotFoundError(f"FORENSICS_ROOT={env} does not contain {CONFIG_RELPATH}")
    here = (start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / CONFIG_RELPATH).exists():
            return candidate
    raise FileNotFoundError(
        f"Could not find {CONFIG_RELPATH} in {here} or any parent; run from inside the "
        "forensic-stats checkout or set FORENSICS_ROOT."
    )


@dataclass(frozen=True)
class HttpConfig:
    contact: str
    user_agent_prefix: str
    default_timeout_seconds: float
    rate_limits: dict[str, float] = field(default_factory=dict)
    never_refetch: bool = True

    @property
    def contact_is_placeholder(self) -> bool:
        return (not self.contact.strip()) or PLACEHOLDER_MARKER in self.contact

    def user_agent(self, purpose: str = "") -> str:
        ua = f"{self.user_agent_prefix} ({self.contact})"
        return f"{ua} {purpose}".strip()

    def rate_limit_for(self, host: str) -> float:
        return float(self.rate_limits.get(host, self.rate_limits.get("default", 1.0)))


def _deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@lru_cache(maxsize=8)
def load_config(root: Path | None = None) -> HttpConfig:
    root = root or find_repo_root()
    with open(root / CONFIG_RELPATH, "rb") as fh:
        raw = tomllib.load(fh)
    local = root / LOCAL_CONFIG_RELPATH
    if local.exists():
        with open(local, "rb") as fh:
            raw = _deep_merge(raw, tomllib.load(fh))
    http = raw.get("http", {})
    return HttpConfig(
        contact=str(http.get("contact", "")),
        user_agent_prefix=str(http.get("user_agent_prefix", "forensic-stats/0.1")),
        default_timeout_seconds=float(http.get("default_timeout_seconds", 120)),
        rate_limits={str(k): float(v) for k, v in raw.get("rate_limits", {}).items()},
        never_refetch=bool(raw.get("cache", {}).get("never_refetch", True)),
    )


def require_contact(root: Path | None = None) -> HttpConfig:
    """Return the HTTP config, or raise ContactNotConfigured with an actionable message."""
    cfg = load_config(root)
    if cfg.contact_is_placeholder:
        raise ContactNotConfigured(
            "config/forensics.toml still has the placeholder contact string. Network fetches "
            "refuse to run until [http].contact holds a real name and email (SEC EDGAR requires "
            "it; we apply the same policy to every host). Edit config/forensics.toml or create "
            "config/forensics.local.toml containing:\n\n"
            '[http]\ncontact = "Your Name you@example.org"\n'
        )
    return cfg
