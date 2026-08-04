"""
Canonical record model - provider-neutral

SpatiumDDI is the source of truth. Azure Private DNS and Cloudflare are reconciled edges

Value canonicalization lives here, not in adapters: A/AAAA values are validated and normalized via `ipaddress` (case, zero-compressed)
CNAME/PTR targets are lowercased with trailing dots dropped, and TXT content stays opaque
 - only surrounding whitespace (an adapter artifact) is stripped
"""
from dataclasses import dataclass, field
from ipaddress import AddressValueError, IPv4Address, IPv6Address
from typing import TypeAlias

RecordKey: TypeAlias = tuple[str, str, str]
SUPPORTED_RECORD_TYPES = frozenset({"A", "AAAA", "CNAME", "PTR", "TXT"})
DOMAIN_VALUE_RECORD_TYPES = frozenset({"CNAME", "PTR"})

def canonical_record_key(zone: str, name: str, rtype: str) -> RecordKey:
    return (
        zone.strip().rstrip(".").lower(),
        name.strip().rstrip(".").lower(),
        rtype.strip().upper(),
    )

def _canonical_value(rtype: str, value: str) -> str:
    if rtype == "A":
        try:
            return str(IPv4Address(value))
        except AddressValueError as exc:
            raise ValueError(f"invalid A record value: {value!r}") from exc
    if rtype == "AAAA":
        try:
            address = (IPv6Address(value))
        except AddressValueError as exc:
            raise ValueError(f"invalid AAAA record value: {value!r}") from exc
        if address.scope_id is not None:
            raise ValueError(f"invalid AAAA record value: {value!r}")
        return str(address)
    if rtype in DOMAIN_VALUE_RECORD_TYPES:
        return value.rstrip(".").lower()
    return value  # TXT: content is opaque; case and dots are significant

@dataclass(frozen=True)
class CanonicalRecord:
    zone: str
    name: str
    rtype: str
    values: tuple[str, ...]
    ttl: int = 300

    def __post_init__(self) -> None:
        zone, name, rtype = canonical_record_key(self.zone, self.name, self.rtype)

        if not zone:
            raise ValueError("zone is required")
        if not name:
            raise ValueError("name is required")
        if not rtype:
            raise ValueError("rtype is required")
        if rtype not in SUPPORTED_RECORD_TYPES:
            raise ValueError(f"unsupported record type: {rtype!r}")
        if isinstance(self.ttl, bool) or not isinstance(self.ttl, int) or self.ttl < 0:
            raise ValueError("ttl must be a non-negative integer")
        if not self.values:
            raise ValueError("values are required")
        if any(not isinstance(value, str) for value in self.values):
            raise ValueError("record values must be non-empty strings")

        stripped = tuple(value.strip() for value in self.values)
        if any(not value for value in stripped):
            raise ValueError("record values must be non-empty strings")

        values = tuple(sorted({_canonical_value(rtype, value) for value in stripped}))
        # Re-check emptiness: canonicalization can erase a value (CNAME ".")
        if any(not value for value in values):
            raise ValueError("record values must be non-empty strings")
        if rtype == "CNAME" and len(values) != 1:
            raise ValueError("CNAME records must have exactly one value")

        object.__setattr__(self, "zone", zone)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "rtype", rtype)
        object.__setattr__(self, "values", values)

    @property
    def key(self) -> RecordKey:
        """Identity key: two records with the same key are the 'same' record
        and diff only in values/ttl (an UPDATE, not ADD and DELETE)"""
        return RecordKey(self.zone, self.name, self.rtype)

@dataclass(frozen=True)
class RecordUpdate:
    """One drifted RRset: `desired` is SpatiumDDI truth;
    `actual` is what the edge currently serves"""
    desired: CanonicalRecord
    actual: CanonicalRecord

@dataclass
class Diff:
    to_add: list[CanonicalRecord] = field(default_factory=list)
    to_delete: list[CanonicalRecord] = field(default_factory=list)
    to_update: list[RecordUpdate] = field(default_factory=list)

    @property
    def is_converged(self) -> bool:
        return not (self.to_add or self.to_update or self.to_delete)