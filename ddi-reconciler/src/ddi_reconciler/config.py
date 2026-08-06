"""Load reconciler configuration (config.toml) — no secrets in the file.

Secrets/identity come from the environment at provider-construction time:
SPATIUM_API_TOKEN, CLOUDFLARE_API_TOKEN, AZURE_SUBSCRIPTION_ID.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from ddi_reconciler.model import RecordKey, canonical_record_key


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


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    edges: list[EdgeConfig] = []
    for entry in raw.get("edges", []):
        try:
            edge = EdgeConfig(
                name=entry["name"],
                provider=entry["provider"],
                zone=entry["zone"].strip().rstrip(".").lower(),
                managed_keys=frozenset(
                    canonical_record_key(zone, name, rtype)
                    for zone, name, rtype in entry["managed_keys"]
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"invalid edge entry {entry!r}: {exc}") from exc
        if edge.provider not in {"azure", "cloudflare"}:
            raise ConfigError(f"unknown provider {edge.provider!r} for edge {edge.name!r}")
        edges.append(edge)
    if not edges:
        raise ConfigError("config declares no edges")

    return Config(
        spatium_base_url=raw.get("spatium", {}).get("base_url", "http://localhost:8000"),
        azure_resource_group=raw.get("azure", {}).get("resource_group", "rg-cham-lab"),
        edges=tuple(edges),
    )
