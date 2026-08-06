"""Load reconciler configuration (config.toml) — no secrets in the file.

Secrets/identity come from the environment at provider-construction time:
SPATIUM_API_TOKEN, CLOUDFLARE_API_TOKEN, AZURE_SUBSCRIPTION_ID.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from ddi_reconciler.model import RecordKey, canonical_name, canonical_record_key


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class EdgeConfig:
    name: str
    provider: str  # "azure" | "cloudflare"
    zone: str
    managed_keys: frozenset[RecordKey]


@dataclass(frozen=True)
class Config:
    spatium_base_url: str
    azure_resource_group: str
    edges: tuple[EdgeConfig, ...]


def _require_str(entry: dict, field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"invalid edge entry {entry!r}: {field!r} must be a non-empty string")
    return value.strip()


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    edges: list[EdgeConfig] = []
    seen_names: set[str] = set()
    for entry in raw.get("edges", []):
        if not isinstance(entry, dict):
            raise ConfigError(f"invalid edge entry {entry!r}: expected a table")
        name = _require_str(entry, "name")
        provider = _require_str(entry, "provider")
        # Same canonicalizer the managed keys use, so the two agree exactly.
        zone = canonical_name(_require_str(entry, "zone"))

        raw_keys = entry.get("managed_keys")
        if not isinstance(raw_keys, list) or not raw_keys:
            raise ConfigError(
                f"invalid edge entry {entry!r}: 'managed_keys' must be a non-empty list")
        try:
            managed_keys = frozenset(
                canonical_record_key(key_zone, key_name, key_rtype)
                for key_zone, key_name, key_rtype in raw_keys
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"invalid edge entry {entry!r}: {exc}") from exc

        if provider not in {"azure", "cloudflare"}:
            raise ConfigError(f"unknown provider {provider!r} for edge {name!r}")
        # An edge may only own keys in its own zone. Caught here rather than
        # deep inside diff_records, which is after provider credentials have
        # been read and the edge API has already been called.
        foreign = sorted(key for key in managed_keys if key[0] != zone)
        if foreign:
            raise ConfigError(
                f"edge {name!r}: managed_keys outside the edge zone {zone!r}: {foreign}")
        # Duplicate names collapse in the CLI's {edge.name: provider} dict and
        # hand one edge another edge's provider (and therefore another zone).
        if name in seen_names:
            raise ConfigError(f"duplicate edge name: {name!r}")
        seen_names.add(name)

        edges.append(EdgeConfig(name=name, provider=provider, zone=zone,
                                managed_keys=managed_keys))
    if not edges:
        raise ConfigError("config declares no edges")

    return Config(
        spatium_base_url=raw.get("spatium", {}).get("base_url", "http://localhost:8000"),
        azure_resource_group=raw.get("azure", {}).get("resource_group", "rg-cham-lab"),
        edges=tuple(edges),
    )
