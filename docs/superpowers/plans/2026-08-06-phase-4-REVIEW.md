---
phase: 04-cloudflare-reconciler-v2
reviewed: 2026-08-06T00:00:00Z
depth: deep
status: issues
files_reviewed: 26
files_reviewed_list:
  - ddi-reconciler/src/ddi_reconciler/cli.py
  - ddi-reconciler/src/ddi_reconciler/config.py
  - ddi-reconciler/src/ddi_reconciler/desired_file.py
  - ddi-reconciler/src/ddi_reconciler/model.py
  - ddi-reconciler/src/ddi_reconciler/reconcile.py
  - ddi-reconciler/src/ddi_reconciler/runner.py
  - ddi-reconciler/src/ddi_reconciler/providers/spatium.py
  - ddi-reconciler/src/ddi_reconciler/providers/azure.py
  - ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py
  - ddi-reconciler/src/ddi_reconciler/providers/__init__.py
  - ddi-reconciler/src/ddi_reconciler/__init__.py
  - ddi-reconciler/config.toml
  - ddi-reconciler/pyproject.toml
  - ddi-reconciler/tests/test_cli.py
  - ddi-reconciler/tests/test_config.py
  - ddi-reconciler/tests/test_desired_file.py
  - ddi-reconciler/tests/test_runner.py
  - ddi-reconciler/tests/test_provider_spatium.py
  - ddi-reconciler/tests/test_provider_azure.py
  - ddi-reconciler/tests/test_provider_cloudflare.py
  - terraform/cloudflare/main.tf
  - terraform/cloudflare/variables.tf
  - terraform/cloudflare/terraform.tfvars.example
  - terraform/modules/hub/main.tf
  - terraform/modules/hub/cloud-init.yml.tpl
  - .gitignore
findings:
  critical: 6
  warning: 13
  info: 9
  total: 28
passes:
  - primary deep review (cross-file, call-chain, security)
  - adversarial mutation-path audit (independent, reproduction-driven)
---

# Phase 4: Code Review Report (deep)

**Reviewed:** 2026-08-06
**Depth:** deep (whole-file final state, cross-module call-chain tracing, empirical reproduction)
**Files Reviewed:** 26
**Status:** issues_found
**Baseline:** `7337b29..94912f9`, 78 tests passing, `terraform fmt -check -recursive` clean, `ruff` not installed in this environment.

## Summary

The core model and diff engine are genuinely strong: `canonical_record_key` is applied consistently by all three adapters, the apex `"@"` convention agrees across Spatium/Azure/Cloudflare, the `managed_keys` allowlist is enforced twice (`plan_edge` on desired, `diff_records` on actual), and value canonicalization prevents the classic false-drift cases. I could not construct a Spatium payload, snapshot, or edge API response that made `diff_records` emit a change for a key outside the allowlist.

The defects are all one layer out from the diff engine, in the places the allowlist does not reach:

1. The allowlist bounds *which* keys can change; nothing bounds *whether the desired set is trustworthy*. An empty or partial truth response is indistinguishable from "these records should not exist," and `--apply` deletes them and **exits 0**. This is the data-loss path (CR-1).
2. The allowlist bounds keys, not zones-at-the-API. The Cloudflare adapter never checks `record.zone` against the zone it was constructed for, and `load_config` allows duplicate edge names — which together produce a reproducible write into an entirely unrelated zone (CR-4).
3. Cloudflare's create-before-delete fan-out is correct for multi-value A RRsets and **structurally impossible** for CNAME, which is the one CNAME in `config.toml` (CR-2).
4. The one new NSG rule uses a wildcard destination in an NSG whose own comment, 40 lines above, forbids exactly that (CR-3).

5. Cloudflare collapses an RRset to a single TTL taken from whichever record the API returned first, so TTL drift on the other values is invisible to the diff, to `--dry-run`, and to the post-apply verification alike — converged forever, exit 0 (CR-5).
6. Azure auto-registered records are hidden from the diff but not from writes: a colliding managed key reads as absent, becomes an ADD, and `create_or_update` replaces the VM's registration — exit 0 (CR-6).

Thirteen warnings cover ownership-adjacent gaps (zone-lookup trust, pagination, truth-side pagination and snapshot poisoning, the unreachable desired-side guard, TXT quote asymmetry, and the drift workflow's broken invocation), and nine info items cover polish and test quality.

**A structural note worth carrying into Phase 5.** Two independent passes converged on the same shape: the diff engine and the allowlist are sound, and every serious defect lives at a boundary the allowlist does not reach. The allowlist answers *which keys may change*. Nothing answers *whether the desired set is trustworthy* (CR-1, WR-11), *whether the provider is pointed at the right zone* (CR-4), *whether what `fetch_actual` returned is the whole truth* (CR-5, WR-5), or *whether a record the diff cannot see is nevertheless writable* (CR-6). `apply_edge`'s post-apply verification inherits that blindness exactly: it re-plans through the same `fetch_actual`, so it can never detect a drift the fetch cannot represent. The verification is exactly as strong as the fetch.

The Summary's earlier claim that "the allowlist is enforced twice" holds on the *actual* side only. On the *desired* side the two layers mask each other — see WR-12.

---

## Critical Issues

### CR-1: An empty or partial desired set deletes every managed record and exits 0 **[reproduced]**

**Files:** `ddi-reconciler/src/ddi_reconciler/providers/spatium.py:45-65`, `ddi-reconciler/src/ddi_reconciler/reconcile.py:82-84`, `ddi-reconciler/src/ddi_reconciler/runner.py:37-45`, `ddi-reconciler/src/ddi_reconciler/cli.py:107-123`

**Issue:** There is no distinction between "truth says this record should not exist" and "truth did not tell us anything." `SpatiumProvider.fetch_desired` iterates the `/api/v1/dns/zones` listing and only emits records for zones present in that listing; a configured zone that is *absent* from the listing produces zero records and **no exception**. `diff_records` then classifies every managed actual record as `to_delete`, `apply_edge` deletes them, the post-apply re-check passes (they really are gone), and `main` returns 0.

**Failure scenario (both reproduced):**

*(a) Spatium reachable, zone missing.* The laptop's SpatiumDDI DB is reset / the zone is renamed / the API token is re-scoped to fewer zones:

```
=========== R11: Spatium: configured zone absent from /zones ===========
fetch_desired returned: [] (no exception raised)
```

*(b) Stale, empty, or truncated `--desired-from-file` snapshot* (the ADR-006 CI path). With the repo's real Cloudflare managed keys and a `[]` snapshot:

```
=========== R1: Empty desired snapshot + --apply ===========
[cf] DELETE demo CNAME www.dwsolution.co ttl=300
[cf] DELETE reconciler-check TXT ok ttl=300
summary: 0 add, 0 update, 2 delete across 1 edge(s) - applied
exit: 0
DELETED: [('dwsolution.co', 'demo', 'CNAME'), ('dwsolution.co', 'reconciler-check', 'TXT')]
remaining at edge: []
```

Exit code 0 means a CI job or an operator sees a clean success while public DNS records were destroyed.

**Why it matters:** This is the only path in the codebase that loses production data, and it reports success while doing it. The `managed_keys` allowlist bounds the blast radius to the allowlisted keys — but bounding the blast radius is not the same as not detonating.

**Fix:**

```python
# spatium.py — fail closed on a zone truth does not know about
def fetch_desired(self, zones: set[str]) -> list[CanonicalRecord]:
    wanted = {z.strip().rstrip(".").lower() for z in zones}
    seen: set[str] = set()
    ...
    for zone in self._get(ZONES_PATH):
        zone_name = ...
        if zone_name not in wanted:
            continue
        seen.add(zone_name)
        ...
    missing = wanted - seen
    if missing:
        raise RuntimeError(
            f"spatium does not serve configured zone(s): {', '.join(sorted(missing))}; "
            "refusing to treat an unknown zone as empty truth")
```

```python
# runner.py — refuse a wholesale prune without explicit opt-in
def apply_edge(edge, desired_all, provider, *, allow_prune: bool = False) -> EdgeResult:
    result = plan_edge(edge, desired_all, provider)
    if result.diff.is_converged:
        return result
    pruning_everything = (
        result.diff.to_delete
        and not result.diff.to_add
        and not result.diff.to_update
        and len(result.diff.to_delete) == len(edge.managed_keys)
    )
    if pruning_everything and not allow_prune:
        raise ConvergenceError(
            f"edge {edge.name!r}: desired state is empty for every managed key; "
            "this would delete all owned records. Re-run with --allow-prune if intended.")
    ...
```

Also add to `desired_file.load_desired`: reject a zero-length snapshot (`raise ValueError("desired snapshot is empty")`) — a committed snapshot for this project always has at least three records.

---

### CR-2: Cloudflare `apply()` creates before deleting, so the managed `demo` CNAME can never be retargeted **[reproduced]**

**File:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:132-139`

**Issue:** For `to_update`, the adapter POSTs every added value (line 132-133) before DELETEing every removed value (line 134-139). That ordering is correct and outage-free for a multi-value A RRset. It is impossible for a CNAME: DNS forbids two CNAMEs at the same owner name and Cloudflare enforces it (error 81053, "An A, AAAA, or CNAME record with that host already exists"). `config.toml:26` makes `["dwsolution.co", "demo", "CNAME"]` a managed key — a target change is the single most likely mutation this adapter will ever be asked to perform.

**Failure scenario [reproduced]:** truth changes `demo` from `old.example.com` to `new.example.com`:

```
=========== R4: Cloudflare CNAME target change ===========
RuntimeError: cloudflare API 400 on /zones/zid/dns_records:
  [{'code': 81053, 'message': 'An A, AAAA, or CNAME record with that host already exists.'}]
DELETE(old CNAME) call_count: 0 <- old record never removed
request order: [('GET','zones?name=dwsolution.co'), ('GET','dns_records?...'), ('POST','dns_records')]
```

`apply` aborts on the first POST, the DELETE never runs, `apply_edge` propagates the `RuntimeError`, and `main` exits 1. Every subsequent run repeats identically. The reconciler is permanently unable to converge its primary Cloudflare record, and no test covers a CNAME value change (`test_apply_fans_out_add_and_delete_per_value` uses type A).

**Fix:** for a 1:1 value replacement, PATCH the existing record's content instead of POST+DELETE — this is also atomic and avoids the transient double-record window on A RRsets:

```python
for update in diff.to_update:
    want, have = update.desired, update.actual
    existing = {self._match_key(want.rtype, self._content(r)): r
                for r in self._api_records.get(want.key, [])}
    added   = sorted(set(want.values) - set(have.values))
    removed = sorted(set(have.values) - set(want.values))

    # 1:1 replacement (always the case for CNAME) -> in-place PATCH
    while added and removed:
        old, new = removed.pop(0), added.pop(0)
        if old not in existing:
            raise RuntimeError(...)
        self._request("PATCH", f"/zones/{zone_id}/dns_records/{existing[old]['id']}",
                      json={"content": new, "ttl": want.ttl})
        existing.pop(old)
    for value in added:
        self._create(want, value)
    for value in removed:
        ...  # unchanged delete path
```

Add a regression test: CNAME `demo` old target -> new target must issue exactly one PATCH and zero POSTs.

---

### CR-3: NSG `AllowHTTPInternal` uses a wildcard destination, contradicting the invariant documented 40 lines above it

**File:** `terraform/modules/hub/main.tf:99-109` (violating the contract at `terraform/modules/hub/main.tf:55-59`)

**Issue:** Lines 55-59 state the NSG's design rule verbatim:

> Rules 100-120 are destination-scoped to the hub VM, not `"*"`: this NSG is associated to BOTH hub subnets, so a wildcard destination would silently extend SSH/WireGuard/DNS exposure to anything later placed in `snet-shared`.

The new rule 125 sets `destination_address_prefix = "*"` — the exact construct that comment forbids — while every other allow rule in the NSG is scoped to `var.hub_vm_ip`, `var.wg_transfer_cidr`, `var.onprem_address_space`, or `Internet`. The NSG is associated to both `snet-vpn` and `snet-shared` (lines 209-217), and `terraform/modules/hub/outputs.tf:6` exports `shared_subnet_id`, so `snet-shared` is explicitly published for callers to place workloads in.

**Failure scenario:** a future task places any resource in `snet-shared` (a spoke jumpbox, a test app, the SpatiumDDI container). That resource becomes inbound-TCP/80-reachable from `10.10.0.0/16`, `10.20.0.0/16`, and `172.16.0.0/24` — the last being the WireGuard transfer network, i.e. every WireGuard peer, including any future peer added to `wg0.conf`. Rule 125 is evaluated at priority 125, well before `DenyAllOtherInbound` at 4000, so nothing downstream re-narrows it. The plan (`2026-07-31-phase-4-cloudflare-reconciler-v2.md:1521`) specified `"*"`, so this was copied faithfully; the plan is what is wrong, and the in-file invariant should have taken precedence.

Compounding it, the source prefixes are hardcoded string literals that duplicate `var.onprem_address_space` and `var.wg_transfer_cidr` defaults. An operator who sets `wg_transfer_cidr = "172.16.5.0/24"` gets a rule that (a) silently stops allowing HTTP from the tunnel and (b) keeps a stale allow for `172.16.0.0/24`. Both other multi-prefix rules (120, 130-140) correctly reference the variables.

**Fix:**

```hcl
  security_rule {
    name                    = "AllowHTTPInternal"
    priority                = 125
    direction               = "Inbound"
    access                  = "Allow"
    protocol                = "Tcp"
    source_port_range       = "*"
    destination_port_range  = "80"
    source_address_prefixes = [
      var.address_space,          # hub VNet (not a hardcoded 10.10.0.0/16)
      var.onprem_address_space,
      var.wg_transfer_cidr,
    ]
    destination_address_prefix = var.hub_vm_ip   # was "*"
  }
```

Note the deviation from the plan brief in the PR description so the plan gets amended rather than re-applied.

---

### CR-4: Cloudflare adapter ignores both its `zones` argument and `record.zone` — reachable path writes into an unrelated zone **[reproduced]**

**Files:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:59-60,87-88,115-119,123-125`, `ddi-reconciler/src/ddi_reconciler/config.py:42-58`, `ddi-reconciler/src/ddi_reconciler/cli.py:29-39`

**Issue:** Three independent gaps compose into an ADR-005 ownership breach:

1. `CloudflareProvider.fetch_actual(self, zones)` accepts a `zones` argument and never reads it (line 87-88); it uses `self.zone_name` unconditionally and stamps every returned record with `zone=self.zone_name` (line 105, 110).
2. `_create` builds the target name from `self._fqdn(record.name)` (line 117), which appends `self.zone_name` — it never consults `record.zone`. `to_update` and `to_delete` at least have the `_api_records` state guard (lines 135-138, 142-145, 149-152); **`to_add` has no guard at all**.
3. `load_config` never rejects duplicate edge `name`s, and `_build_providers` keys its result by `edge.name` (cli.py:29-39), so two edges with the same name collapse into one provider — the last one wins — and `providers[edge.name]` at cli.py:113 hands the *wrong-zone* provider to both edges.

**Failure scenario [reproduced]:** a `config.toml` with two `[[edges]]` blocks that share `name = "cf"` (a copy/paste slip, or an edge renamed in one place). Truth contains only `demo` in `dwsolution.co`:

```
=========== R12: Duplicate edge names in config ===========
exit: 1
POST https://api.cloudflare.com/client/v4/zones/OTHER/dns_records
  {"type":"CNAME","name":"demo.other-tenant.example","content":"www.dwsolution.co","ttl":300,"proxied":false}
posts: 1
```

A record was created in `other-tenant.example` — a zone that is in neither `managed_zones` nor `managed_keys` for that edge. The non-zero exit comes only from the *post-apply* convergence check; the write already happened. The unguarded `to_add` path is confirmed independently:

```
=========== R20: to_add has NO zone-consistency guard ===========
record.zone = dwsolution.co -> POST .../zones/OZ/dns_records
body: {"type":"CNAME","name":"demo.other.example",...}
```

**Why it matters:** the whole ADR-005 claim is "the reconciler owns only the allowlisted `(zone, name, rtype)` keys." Here the key was allowlisted but the *zone it landed in* was not. The Azure adapter is correct by comparison — it passes `record.zone` into every SDK call (azure.py:76, 80) — so the two adapters do not agree on this contract.

**Fix (all three, they are cheap and independent):**

```python
# config.py, after the edge loop
names = [e.name for e in edges]
dupes = {n for n in names if names.count(n) > 1}
if dupes:
    raise ConfigError(f"duplicate edge name(s): {', '.join(sorted(dupes))}")
```

```python
# cloudflare.py
def fetch_actual(self, zones: set[str]) -> list[CanonicalRecord]:
    normalized = {z.strip().rstrip(".").lower() for z in zones}
    if normalized != {self.zone_name}:
        raise RuntimeError(
            f"cloudflare provider is bound to {self.zone_name!r} but was asked for {sorted(normalized)}")
    ...

def _create(self, record: CanonicalRecord, value: str) -> None:
    if record.zone != self.zone_name:
        raise RuntimeError(
            f"refusing to write {record.key} into zone {self.zone_name!r}")
    ...

def apply(self, diff: Diff) -> None:
    for record in [*diff.to_add, *(u.desired for u in diff.to_update), *diff.to_delete]:
        if record.zone != self.zone_name:
            raise RuntimeError(f"refusing to mutate {record.key} in zone {self.zone_name!r}")
    ...
```

---

## Warnings

### WR-1: The Azure auto-registration filter inverts into a clobber for a colliding managed key **[reproduced]**

**File:** `ddi-reconciler/src/ddi_reconciler/providers/azure.py:48` with `:72-77` (docstring claim at `:3-5`)

**Issue:** `fetch_actual` drops `is_auto_registered=True` record sets, which correctly prevents `to_delete` and `to_update` for them. But dropping them also makes them **invisible to the diff**, so a managed key that collides with an auto-registered name looks *missing* and lands in `to_add` — and `apply` services `to_add` with `create_or_update`, which at the API level is an upsert onto that exact `(resource_group, zone, "A", name)` record set. The module docstring's claim that auto-registered records "can never be updated or deleted" is false for the update direction.

Separately, `getattr(rs, "is_auto_registered", False)` defaults to *unsafe*: if the SDK model for an older API version omits the field, every auto-registered record silently becomes eligible for deletion.

**Failure scenario [reproduced]:** `config.toml:18` manages `["azure.dwsolution.co", "app", "A"]`. A VM whose hostname is `app` auto-registers `app.azure.dwsolution.co -> 10.10.4.99`:

```
=========== R3: Azure auto-registered collision ===========
fetch_actual sees: []
diff to_add: [('azure.dwsolution.co','app','A')] to_delete: []
Azure create_or_update called on the auto-registered name:
  [('azure.dwsolution.co','A','app',{'ttl':300,'a_records':[{'ipv4_address':'10.10.4.30'}]})]
```

Best case Azure rejects the upsert and the edge fails on every run with an opaque `azure API error applying diff`. Worst case it succeeds, the VM's own DNS answer is replaced by a static one, and the VM loses its name.

**Fix:**

```python
auto_registered: set[tuple[str, str]] = set()
...
    if getattr(rs, "is_auto_registered", None) is not False:   # fail closed on a missing field
        auto_registered.add((rs.name.lower(), rtype))
        continue
...
# in plan_edge / apply path, or as a provider attribute the runner consults:
collisions = {k for k in edge.managed_keys if (k[1], k[2]) in provider.auto_registered}
if collisions:
    raise RuntimeError(
        f"managed key(s) {sorted(collisions)} collide with Azure auto-registered record sets; "
        "rename the VM or remove the key from managed_keys")
```

### WR-2: `except KeyError` mislabels malformed payloads as missing environment variables **[reproduced]**

**File:** `ddi-reconciler/src/ddi_reconciler/cli.py:124-126`

**Issue:** The handler is unscoped and assumes every `KeyError` reaching `main` came from `os.environ[...]`. Two production paths raise `KeyError` from data, not the environment: `desired_file.load_desired` (`e["zone"] / e["rtype"] / e["values"] / e["ttl"]`, desired_file.py:27-29) and `SpatiumProvider.fetch_desired` (`zone["name"]`, `zone["id"]`, `rec["type"]`, `rec["name"]`, `rec["value"]`, spatium.py:49-60). The Spatium case is not hypothetical — the module docstring at spatium.py:4-6 explicitly calls the endpoint/field shape "a per-deployment seam," so a field-name mismatch is the *expected* first failure against a real stack.

**Failure scenario [reproduced]:** a hand-edited or partially written `desired-records.json` entry missing `"ttl"`:

```
=========== R2: Malformed snapshot (missing 'ttl') ===========
error: missing required environment variable: ttl
exit: 1
```

The operator is sent to check environment variables for a problem in a JSON file.

**Fix:** read env vars explicitly and drop the broad handler.

```python
def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"missing required environment variable: {name}")
    return value
```

Then remove `except KeyError` entirely so a genuine data `KeyError` surfaces as a real (traceable) bug, or wrap `load_desired`/`fetch_desired` so it becomes `ValueError(f"malformed record entry: missing field {exc.args[0]!r}")`.

### WR-3: Adapters canonicalize the entire zone before the ownership filter, so one unmanaged bad record kills the run **[reproduced]**

**Files:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:101-113`, `ddi-reconciler/src/ddi_reconciler/providers/azure.py:44-55`, filtered downstream at `ddi-reconciler/src/ddi_reconciler/reconcile.py:64-71`

**Issue:** Both `fetch_actual` implementations construct a `CanonicalRecord` for *every* supported-type record in the zone. `CanonicalRecord.__post_init__` is a strict validator. The ownership filter runs later, in `diff_records`. So a record the reconciler explicitly disclaims ownership of can abort the entire reconcile.

**Failure scenario [reproduced]:** somebody else's TXT record in `dwsolution.co` whose content is whitespace-only (`"  "` as returned quoted by the API):

```
=========== R14: One UNMANAGED malformed record aborts the whole reconcile ===========
ValueError: record values must be non-empty strings  <- managed 'demo' record never even reached
```

Azure has the same shape, plus worse diagnostics — an RRset whose `ipv4_address` is `None` raises a bare `ValueError` that escapes the `azure API error listing {zone}` wrapper (which only wraps the `list()` call at azure.py:41-43):

```
=========== R15: Azure record set with a null value ===========
ValueError: record values must be non-empty strings  <- no zone/record-name context
```

The CLI turns both into `error: record values must be non-empty strings` with nothing identifying the offending record.

**Fix:** canonicalize per record inside a `try`, and carry identity into the message:

```python
try:
    records.append(CanonicalRecord(zone=z, name=n, rtype=t, values=..., ttl=...))
except ValueError as exc:
    if (z, n, t) in self.managed_keys:      # pass the allowlist into the provider
        raise RuntimeError(f"managed record {z}/{n}/{t} is malformed at the edge: {exc}") from exc
    continue                                 # unowned + unparseable -> not our problem
```

### WR-4: `_zone()` trusts `result[0]` without verifying the zone name **[reproduced]**

**File:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:44-50`

**Issue:** `_zone()` checks only that `result` is non-empty and takes `result[0]["id"]`. It never asserts `result[0]["name"] == self.zone_name`, and it never handles `len(result) > 1`. This zone id is then used for every read **and every DELETE**.

**Failure scenario [reproduced]:** a token with access to several zones plus any change to Cloudflare's `?name=` matching (or an operator-side typo that makes the filter non-exact) silently retargets a destructive tool:

```
=========== R13: multi-result / mismatched zone accepted blindly ===========
zone id chosen: WRONGZONE (no name verification)
```

Once `_zone()` caches `WRONGZONE`, `fetch_actual` reads that zone (yielding an empty/foreign actual set) and `apply`'s `to_delete` loop would DELETE record ids in it.

**Fix:**

```python
def _zone(self) -> str:
    if self._zone_id is None:
        result = self._request(
            "GET", f"/zones?name={urllib.parse.quote(self.zone_name, safe='')}")["result"]
        exact = [z for z in result if z.get("name", "").strip().rstrip(".").lower() == self.zone_name]
        if len(exact) != 1:
            raise RuntimeError(
                f"cloudflare API error: expected exactly one zone named {self.zone_name!r}, "
                f"got {[z.get('name') for z in result]}")
        self._zone_id = exact[0]["id"]
    return self._zone_id
```

The `quote()` also closes R16: `self.zone_name` is interpolated raw into the query string today, so a config value like `dwsolution.co&per_page=1` yields `/zones?name=dwsolution.co&per_page=1`.

### WR-5: Pagination stops at page 1 when `result_info` is absent and crashes when it is null **[reproduced]**

**File:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:95`

**Issue:** `body.get("result_info", {}).get("total_pages", 1)` has two failure modes. `result_info` absent -> `total_pages` defaults to 1 -> the loop stops after 100 records. `result_info: null` -> `.get` on `None` -> `AttributeError`, which is *not* in `main`'s handled tuple (cli.py:127), so the operator gets a raw traceback instead of `error: ...`.

**Failure scenario [reproduced]:**

```
=========== R6: Cloudflare pagination ===========
no result_info -> records fetched: 1 (stops after page 1)
UNCAUGHT-BY-CLI-CONTRACT: AttributeError 'NoneType' object has no attribute 'get'
```

For a public zone with >100 records, a truncated page-1 read makes a managed record that lives on page 2 look *missing*: the diff emits `to_add`, `_create` POSTs a duplicate value into an RRset that already has it, and `_api_records` never held the real record so nothing detects the duplication. `>1`-page pagination has no test at all (`register_records()` in test_provider_cloudflare.py:20-23 always sets `total_pages=1`).

**Fix:**

```python
info = body.get("result_info") or {}
total_pages = info.get("total_pages")
if total_pages is None:
    if not body["result"]:
        break
    page += 1
    continue
if page >= total_pages:
    break
page += 1
```

Add a two-page test asserting records from both pages appear in `_api_records`.

### WR-6: `_match_key` does not mirror `CanonicalRecord`'s value normalization for TXT or A **[reproduced]**

**Files:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:69-84` vs `ddi-reconciler/src/ddi_reconciler/model.py:69,73`

**Issue:** The comment at cloudflare.py:71-74 claims `_match_key` mirrors "CanonicalRecord's domain-value normalization." It mirrors CNAME/PTR and AAAA, but the model *also* applies `value.strip()` to every value (model.py:69) before canonicalization, and normalizes A through `IPv4Address`. `_match_key` returns TXT and A content raw. So the `existing` index in `apply()` can be keyed on a string the canonical value will never equal.

**Failure scenario [reproduced]:** a managed TXT record stored at Cloudflare with a trailing space inside the quotes (a very common copy/paste artifact in TXT values):

```
=========== R5: Cloudflare TXT with inner whitespace ===========
canonical actual values: ('stale value',)
RuntimeError: cloudflare API state error: value 'stale value' not in fetched index for
  ('dwsolution.co','reconciler-check','TXT'); apply() requires fetch_actual() in the same run
```

The error message actively misdiagnoses the cause — `fetch_actual()` *was* called in the same run. `reconciler-check` TXT is one of only two Cloudflare managed keys, so this affects half the Cloudflare surface, and it exits 1 on every run.

**Fix:** export the model's canonicalizer and reuse it, so drift between the two is structurally impossible:

```python
# model.py
def canonical_value(rtype: str, value: str) -> str:
    return _canonical_value(rtype, value.strip())

# cloudflare.py
@staticmethod
def _match_key(rtype: str, content: str) -> str:
    try:
        return canonical_value(rtype, content)
    except ValueError:
        return content   # unparseable -> raw, as today
```

### WR-7: `load_config` accepts semantically invalid edges; some raise uncaught **[reproduced]**

**File:** `ddi-reconciler/src/ddi_reconciler/config.py:42-58`

**Issue:** Three validation gaps:

1. **Managed keys are not checked against the edge's own zone.** A `cloudflare` edge with `zone = "dwsolution.co"` and `managed_keys = [["azure.dwsolution.co","app","A"]]` loads cleanly and only fails much later inside `diff_records` (reconcile.py:53-55) — after `_build_providers` has already read `CLOUDFLARE_API_TOKEN` and after `fetch_actual` has already hit the API:
   ```
   === R17 === load_config accepted edge with foreign managed key:
     frozenset({('azure.dwsolution.co','app','A')})
   ```
2. **`AttributeError` is not caught** (line 54). `entry["zone"].strip()` on a TOML integer escapes both the local handler and `main`'s handler:
   ```
   === R7 === UNCAUGHT: AttributeError 'int' object has no attribute 'strip'
   ```
   The exit code is still 1 (uncaught exceptions exit 1), but the operator gets a traceback instead of `error: invalid edge entry`.
3. **Duplicate edge names are accepted** — the enabler for CR-4.

**Fix:** add `AttributeError` to the caught tuple at line 54, validate `key[0] == edge.zone` for every managed key at load time, and reject duplicate names (snippet in CR-4).

### WR-8: Partial apply leaves mixed state with no summary of what changed **[reproduced]**

**Files:** `ddi-reconciler/src/ddi_reconciler/cli.py:111-122`, `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:123-154`, `ddi-reconciler/src/ddi_reconciler/providers/azure.py:72-82`

**Issue:** The per-edge loop has no `finally` and no per-edge status line; the summary at cli.py:121 is only reached if every edge succeeds. A mid-loop failure exits 1 with the operator's only evidence being the diff lines already streamed for the successful edges.

**Failure scenario [reproduced]:** two edges, the first applies, the second's provider raises a transient API 500:

```
=========== R9: Partial apply across edges ===========
[e1] ADD    app A 10.10.4.30 ttl=300
exit: 1 | edge e1 already mutated: [[('azure.dwsolution.co','app','A')]]
```

Within a single provider it is worse: `cloudflare.apply` can create some values and delete only some of an RRset's removed values before raising (cloudflare.py:132-139), and `azure.apply` can complete every upsert and then fail on the deletes (azure.py:74-80). There is no retry on transient failures anywhere (both adapters use a bare `requests.Session` / SDK call with `timeout=10` and no backoff).

**Fix:** track per-edge outcomes and always emit the summary:

```python
applied_edges, failed_edge = [], None
try:
    for edge in edges:
        result = run(edge, desired_all, providers[edge.name])
        _print_diff(edge.name, result.diff)
        if args.apply and not result.diff.is_converged:
            applied_edges.append(edge.name)
        ...
except (...) as exc:
    if applied_edges:
        print(f"error: aborted after mutating edge(s): {', '.join(applied_edges)}", file=sys.stderr)
    raise
```

### WR-9: The model validates record *values* rigorously and record *names* not at all **[reproduced]**

**File:** `ddi-reconciler/src/ddi_reconciler/model.py:51-83`

**Issue:** `__post_init__` validates types, TTL, emptiness, per-type value syntax (IPv4/IPv6 parsing, CNAME arity, CNAME-root erasure), but `name` receives only `strip().rstrip(".").lower()` and a non-empty check. Any string survives — spaces, slashes, `..`, arbitrary length. The name is then interpolated into a Cloudflare FQDN body field and an Azure ARM path segment.

**Failure scenario [reproduced]:** a truth record whose Spatium `name` field is malformed:

```
=========== R23 ===========
canonical name accepted from truth: [('dwsolution.co', 'weird name/../', 'A')]
would become fqdn: weird name/../.dwsolution.co
```

This is **not** an exploitable traversal — the Cloudflare name goes in a JSON body, and the Azure SDK URL-quotes path segments (`/` becomes `%2F`). The impact is correctness and diagnosability: garbage from the source of truth propagates all the way to a provider API call, and the resulting rejection surfaces as an opaque `cloudflare API 400` / `azure API error applying diff` with no indication the name was the problem. Given the reconciler is credentialed to mutate production DNS, validating at the truth boundary is the right posture.

**Fix:** in `__post_init__`, after normalization:

```python
_LABEL = re.compile(r"^(\*|[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?)$")
if name != "@":
    labels = name.split(".")
    if len(name) > 253 or not all(_LABEL.match(label) for label in labels):
        raise ValueError(f"invalid DNS name: {name!r}")
```

### WR-10: TTL is never range-checked per edge; TTL 0 is POSTed verbatim to Cloudflare **[reproduced]**

**Files:** `ddi-reconciler/src/ddi_reconciler/model.py:62-63`, `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:115-119`

**Issue:** The model deliberately allows `ttl == 0` (and there are two tests locking that in: `test_preserves_explicit_ttl_zero`, `test_fetch_preserves_ttl_zero`), but no adapter validates the value against what its API accepts. Cloudflare accepts `1` (automatic) or `60..86400`.

**Failure scenario [reproduced]:**

```
=========== R19: TTL=0 from Spatium truth ===========
POST body: {"type":"CNAME","name":"demo.dwsolution.co","content":"www.dwsolution.co","ttl":0,"proxied":false}
```

A `ttl: 0` record in SpatiumDDI truth produces a Cloudflare 400 on every `--apply`, forever, with an error that does not name TTL as the cause. The same value going to Azure is accepted, so drift between the two edges is silent until apply.

**Fix:** validate in `CloudflareProvider._create` / the ttl-PATCH path:

```python
if record.ttl != 1 and not (60 <= record.ttl <= 86400):
    raise RuntimeError(
        f"cloudflare rejects ttl={record.ttl} for {record.key}; use 1 (automatic) or 60-86400")
```

---

## Info

### IN-1: `--export` and the normal path ignore `--edge` when fetching truth **[reproduced]**

**Files:** `ddi-reconciler/src/ddi_reconciler/cli.py:42-48`, `:94-98`

`_fetch_desired` builds its zone set from `config.edges`, never the `--edge`-filtered list, and `--export` runs before edge filtering entirely:

```
=========== R10 === exit: 0 | zones queried: {'zones': ['azure.dwsolution.co','dwsolution.co']}
```
(run with `--edge e1`). Harmless today, but it contradicts the intent of `test_edge_filter_builds_only_selected_providers` ("operators don't need env vars for providers they're not using") — they still need Spatium to serve every configured zone. Pass `edges` into `_fetch_desired`.

### IN-2: Bearer token traverses whatever scheme `base_url` specifies **[reproduced]**

**File:** `ddi-reconciler/src/ddi_reconciler/providers/spatium.py:21-25`, `ddi-reconciler/config.toml:8`

```
=========== R22 === scheme: http | Authorization header sent: Bearer SPAT-SECRET
```

Default is `http://localhost:8000`, so impact today is nil. But nothing stops `base_url` from becoming a remote `http://` host, at which point `SPATIUM_API_TOKEN` goes over the wire in cleartext. Warn (or refuse) when the scheme is `http` and the host is not loopback.

*(Confirmed sound: R21 shows neither adapter leaks its token into any error message — `cloudflare API 403 on /zones?name=...` and `spatium API error on /api/v1/dns/zones: 500 ...` both come back token-free. Tokens live in `Session.headers`, never in a URL, and `requests` strips `Authorization` on cross-host redirects.)*

### IN-3: Redundant entries in the handled-exception tuple

**File:** `ddi-reconciler/src/ddi_reconciler/cli.py:127`

`ConfigError` subclasses `ValueError` (config.py:15) and `ConvergenceError` subclasses `RuntimeError` (runner.py:17), so both are already covered by the two generic entries. Harmless, but it reads as broader coverage than exists — `AttributeError` and `TypeError`, which several confirmed paths raise (R6b, R7, R8), are the ones actually missing.

### IN-4: Duplicated guard blocks and a redundant `_zone()` call

**File:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:135-138`, `:142-145`, `:116` vs `:122`

The two "value not in fetched index" guards are byte-identical; extract a `_record_id(existing, value, key)` helper. `apply()` resolves `zone_id = self._zone()` at line 122, then `_create` calls `self._zone()` again at line 116 — cached, so no extra request, but it obscures that `_create` does not use the caller's `zone_id`.

### IN-5: Dead default parameter

**File:** `ddi-reconciler/src/ddi_reconciler/cli.py:21-25`

`_build_providers(config, edges=None)` and the `if edges is None` branch are never exercised in production — `main` always passes `edges` explicitly (line 108). Only test doubles rely on the signature. Either drop the default or note that it exists for the test contract.

### IN-6: Snapshot writes are non-atomic and reads are unvalidated

**File:** `ddi-reconciler/src/ddi_reconciler/desired_file.py:21`, `:24-30`

`path.write_text(...)` truncates in place: an interrupted `--export` (Ctrl-C, disk full) leaves a truncated JSON file that is then CI's source of truth — and per CR-1, a short snapshot means deletions. `load_desired` also does no schema validation (see WR-2). Use `path.with_suffix(".tmp").write_text(...)` + `os.replace(...)`, and validate on load.

Related: `ddi-reconciler/desired-records.json` does not exist in the tree yet even though `desired_file.py:4-5` and the phase plan both treat it as the CI drift-run input. That is Track C work, but until it exists, `--desired-from-file` has no committed input to point at.

### IN-7: nginx is installed but never explicitly enabled, and the page is written before the package

**File:** `terraform/modules/hub/cloud-init.yml.tpl:5-10`, `:68-71`, `:72-80`

`write_files` runs in `cloud_init_modules`, before `packages` installs in `cloud_config_modules`, so `/var/www/html/index.html` is written first. It works only because Debian's `nginx-common` postinst ships `index.nginx-debian.html` rather than overwriting `index.html`, and because the package auto-starts the service. `bind9` is explicitly enabled in `runcmd` (line 75); nginx is not — the inconsistency is the smell. Add `systemctl enable --now nginx` to `runcmd`, and consider a `listen ${hub_vm_ip}:80;` server block so the "INTERNAL" page cannot be served on the public NIC even if the NSG is widened (relevant given CR-3).

### IN-8: `.gitignore` covers `terraform.tfvars` and `*.auto.tfvars` but not `*.tfvars`

**File:** `.gitignore:11-12`

`AGENTS.md:38` makes "never commit ... `terraform.tfvars`, `*.auto.tfvars`" a hard rule, but a file named `lab.tfvars` or `prod.tfvars` (passed via `-var-file`) is not ignored and would be committed. `terraform/cloudflare/terraform.tfvars.example` correctly contains no secret, and `variables.tf` correctly keeps the token out of Terraform entirely (env-sourced) — this is a gap in the net, not a live leak. Change to:

```gitignore
*.tfvars
!*.tfvars.example
```

---

## Adversarial audit — additional findings

A second, independent pass attacked the mutation path with reproduction-driven experiments (offline, `responses`-mocked HTTP and injected SDK fakes, scratch dir only; the repo suite still passes 78/78). It corroborated CR-1 through CR-4 with its own reproductions and found the following, which the primary pass did not report. Numbering continues the sections above.

### CR-5: Cloudflare keeps only the first API record's TTL for an RRset, producing permanent, order-dependent false convergence **[reproduced]**

**Location:** `ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py:107` — `entry = grouped.setdefault(key, {"values": [], "ttl": int(raw["ttl"])})`

Cloudflare stores TTL per API record, so a two-value RRset can legitimately hold two different TTLs (someone edits one value in the dashboard). `fetch_actual` collapses the RRset into one `CanonicalRecord` and keeps only the first record's TTL. Drift on every other record in the set is invisible to `diff_records`, to `--dry-run`, and to `apply_edge`'s post-apply verification alike — the verification re-reads through the same blind fetch.

**Failure scenario [reproduced]:** identical edge data, two API orderings:

```
seed ttls (300, 60)   rc=0  [cloudflare-public] converged (0 changes)
                      final ttls: [('10.0.0.1', 300), ('10.0.0.2', 60)]
seed ttls (60, 300)   rc=0  UPDATE demo A ... ttl=60 -> ttl=300
                      final ttls: [('10.0.0.1', 300), ('10.0.0.2', 300)]
```

Whether the drift is seen at all depends purely on Cloudflare's result ordering. In the first ordering the tool exits 0 forever, nightly drift stays green, and the condition is stable indefinitely. Blast radius is TTL-only, which is why it ranks below CR-1..CR-4 — but "reports converged while not converged" is the failure mode that makes a reconciler untrustworthy, so it is Critical rather than Warning.

**Fix:** either represent per-value TTL, or detect the split and force drift — if `{r["ttl"] for r in group}` has more than one element, emit an update and PATCH every record in the RRset, not just `want.values & have.values`.

---

### CR-6: Azure auto-registered record sets are hidden from the diff but not from writes — the reconciler clobbers a VM's registration and exits 0 **[reproduced]**

*This supersedes WR-1 below, which described the same defect one severity too low. The full-CLI reproduction and the fail-open matrix justify Critical: it is silent destruction of a record the code's own docstring declares out of bounds.*

**Location:** `providers/azure.py:48` (drop at fetch) and `providers/azure.py:75` (`create_or_update` at apply)

`azure.py:3-5` asserts that auto-registered sets "are dropped at fetch time — combined with the managed-key allowlist in `diff_records` they can never be updated or deleted." Dropping them at fetch does not protect them; it makes them **invisible**, so a colliding managed key looks absent, becomes an ADD, and Azure's `create_or_update` is a replace.

**Failure scenario [reproduced]:** VM `app` auto-registers `app.azure.dwsolution.co → 10.10.4.99`; the managed key is `("azure.dwsolution.co","app","A")` — exactly the kind of name that collides.

```
CLI exit code: 0
  | [azure-private] ADD    app A 10.10.4.30 ttl=300
  | summary: 1 add, 0 update, 0 delete across 1 edge(s) — applied
azure calls: [('PUT', 'azure.dwsolution.co', 'A', 'app', {...})]
app record after: ['10.10.4.30'] is_auto_registered= False
```

The guard is also fail-open in both directions — `getattr(rs, "is_auto_registered", False)`:

```
attribute absent entirely      visible=True  -> write issued
is_auto_registered=None        visible=True  -> write issued
is_auto_registered=True        visible=False -> write issued (as ADD)
is_auto_registered='true'      visible=False -> write issued (as ADD)
```

The installed SDK declares `is_auto_registered: Optional[bool]` with read-only visibility, so `None` is a real service-side state, not a hypothetical.

**Fix:** carry auto-registration into the diff instead of hiding it. Keep auto-registered keys in a `blocked_keys` set on the provider and have `apply()` refuse — loudly — any create/update/delete whose key is in it; better, make `diff_records` aware so the plan prints `SKIP app A (auto-registered)` rather than `ADD`. Treat missing or `None` as unknown-and-blocked, not as manual.

---

### WR-11: The truth adapter reads one page and `--export` can write a wipe-order snapshot **[reproduced]**

**Location:** `providers/spatium.py:27-34` (`_get` returns `body["items"]` with no `next`/`total` handling); `cli.py:96-98` (export path)

Two amplifiers of CR-1, each with its own fix. First, `_get` already anticipates a wrapped collection — i.e. a paginated API — but consumes only what page 1 returns; any managed record beyond it is absent from `desired`, and `diff_records` turns "absent from truth" into `to_delete`. (SpatiumDDI's actual response shape could not be verified — stack offline, no source in-repo — so this vector is a precondition, not an observed deployment fact.) Second, and needing no such assumption:

```
rc: 0 | exported 0 records to ...\desired-records.json
snapshot after export : []
```

SpatiumDDI restarted with an empty DB → `--export` writes `[]`, prints `exported 0 records`, exits 0, and the committed ADR-006 snapshot is now a standing wipe order for the next `--apply`.

**Fix:** make `_get` follow pagination and fail loudly if the envelope carries a `total`/`pages` it did not fully consume; make `--export` refuse to overwrite a non-empty snapshot with zero records (or exit non-zero); add a delete ceiling that aborts when a diff would remove 100% of managed keys.

---

### WR-12: `plan_edge`'s pre-filter makes `diff_records`' desired-side guard unreachable, so a snapshot typo silently deletes the live record **[reproduced]**

**Location:** `runner.py:30-31` (silent filter) vs `reconcile.py:57-62` (the guard that would have caught it)

The Summary above counts "the allowlist is enforced twice" as a strength. On the *actual* side it is. On the *desired* side the two layers mask each other: `plan_edge` silently drops any desired record whose key is not in `managed_keys`, so the `ValueError` in `diff_records` written for exactly this case can never fire.

**Failure scenario [reproduced]:** a snapshot — hand-edited, or produced by anything other than `--export` — spells the name as the FQDN instead of zone-relative:

```
direct diff_records([typo]) -> ValueError: desired record is outside managed record set:
                               dwsolution.co/demo.dwsolution.co/A
via plan_edge([typo])       -> no error; diff.to_delete = [('dwsolution.co','demo','A')]

rc=0 | [cloudflare-public] DELETE demo A 10.0.0.5
       edge after: []
```

The desired record was dropped, the key's desired set became empty, and the live record was deleted with exit 0 and no warning. The same silent drop applies to a truth record whose zone or type does not match.

**Fix:** stop pre-filtering by key in `plan_edge` — filter by zone only, pass the rest to `diff_records`, and let the existing guard raise. If truth is legitimately a superset, log every dropped desired record and refuse to delete a managed key whose desired counterpart was dropped.

---

### WR-13: TXT read and write are not inverses, so a quoted value can never round-trip **[reproduced]**

**Location:** `providers/cloudflare.py:62-67` (`_content` unquotes) vs `providers/cloudflare.py:115-119` (`_create` never quotes)

**Failure scenario [reproduced]:** an operator stores an SPF value in SpatiumDDI with the quotes included (`"v=spf1 -all"`) — routine, since that is how the value is published. Against a faithful echo store, three consecutive runs:

```
before: [('reconciler-check.dwsolution.co', 'TXT', 'v=spf1 -all', 300)]
run1 rc=1 | error: edge 'cloudflare-public' still drifted after apply
run2 rc=1 | error: cloudflare API 400: [{'code': 81057, 'message': 'Record already exists.'}]
run3 rc=1 | error: cloudflare API 400: [{'code': 81057, 'message': 'Record already exists.'}]
after : [('reconciler-check.dwsolution.co', 'TXT', '"v=spf1 -all"', 300)]
```

The reconciler creates the quoted record, reads it back through `_content()` — which strips the quotes it just wrote — and declares drift. Nightly drift is red forever while the tool retries a create Cloudflare rejects.

**Fix:** make read and write inverses — quote on create with internal escaping and unquote on read, or do neither and normalize at the model layer. Handle multi-string TXT (`"a" "b"`) explicitly rather than stripping the outer pair.

---

### WR-14: The nightly drift workflow invokes a path that does not exist and cannot distinguish exit 1 from exit 2

**Location:** `.github/workflows/drift.yml:29` (outside this phase's file scope, but it is the consumer the whole exit-code contract was built for)

The workflow runs `python ddi-reconciler/cli.py` — a path that does not exist after the B1 src-layout move; the entry point is `src/ddi_reconciler/cli.py` (or the `cham-reconcile` script). Separately, `continue-on-error: true` plus a check on `outcome == 'failure'` collapses exit 1 and exit 2 into one bucket, so an auth failure opens an issue titled "DNS drift detected" — precisely the distinction Phase 4's contract exists to make.

**Fix:** invoke `uv run cham-reconcile --dry-run --desired-from-file desired-records.json`, capture the numeric exit code explicitly, and branch on `2` (drift → open issue) vs `1` (operational error → fail the job loudly).

---

### IN-9: No IDNA normalization of names

`_relative`/`_fqdn`/`canonical_record_key` lowercase bytes only, so a managed key spelled in unicode and its punycode record at the edge are different identities — the reconciler creates `démo.dwsolution.co` alongside an existing `xn--dmo-hoa.dwsolution.co`. Not reachable from the current ASCII-only `config.toml`. **Fix:** `idna.encode` names at canonicalization time.

---

## What held up under attack

Things I specifically tried to break and could not:

- **The `managed_keys` allowlist against normalization mismatches.** All three adapters and `config.load_config` route through `canonical_record_key` (or produce values that survive it): Spatium `_relative` (spatium.py:36-43), Cloudflare `_relative` (cloudflare.py:52-57), and Azure's raw `rs.name` all agree on the apex `"@"` convention, on case, and on trailing dots. `diff_records` re-normalizes `managed_keys` at line 49-52 rather than trusting the caller, and `plan_edge` independently filters desired by `edge.managed_keys`. I could not construct a config/Spatium/snapshot/edge-API combination that made the diff emit a change for an unallowlisted key. The failures I did find (CR-4) bypass the key check by getting the *zone* wrong at the API layer, not by defeating the key check.
- **Terraform-seeded records.** `www` and `external-check` (terraform/cloudflare/main.tf:37-52) and `db` are absent from `config.toml`'s `managed_keys`; `diff_records`' `managed_actual` filter (reconcile.py:64-71) drops them from `actual` entirely, and `test_unmanaged_record_inside_managed_zone_is_untouched` locks that in.
- **Token handling.** R21: no bearer token appears in any adapter error message; tokens are set on `Session.headers` and never on a URL; `requests` strips `Authorization` on cross-host redirects. Nothing writes a token to the snapshot, the diff output, or `config.toml`. `terraform/cloudflare` correctly sources `CLOUDFLARE_API_TOKEN` from the environment and never from tfvars, and the backend block keeps `storage_account_name`/`subscription_id`/`tenant_id` in a gitignored `*.tfbackend`.
- **TLS/timeout posture.** Both adapters pass `timeout=10` on every request and leave `verify` at its default `True`. No `verify=False` anywhere.
- **Injection into URLs and API paths.** Zone/record names reach Cloudflare through JSON bodies, not path segments; record ids come from the API and go into paths, but the trust boundary there is Cloudflare itself. The one raw interpolation (`/zones?name={self.zone_name}`, R16) is config-controlled and folded into WR-4's fix.
- **Idempotency and false drift.** Value ordering, duplicate values, IPv6 representation, CNAME case/trailing dots, `@` vs FQDN, and TTL-only changes all converge correctly (`test_reconcile.py` covers each, and `apply_edge`'s post-apply re-plan at runner.py:42-44 catches a stubborn provider).
- **Exit-code contract on the paths that work.** `_ArgumentParser.error` correctly converts argparse's default exit 2 into 1 (cli.py:51-59, tested), `--export` returns 0 early, `--dry-run` returns 2 only on drift, `--apply` returns 0 on convergence, and every provider `RuntimeError` lands on the `return 1` path. The contract *does* break on the uncaught `AttributeError`/`TypeError` paths (WR-5, WR-7, and Spatium's dict-without-`items` body), but only in message quality — Python still exits 1.
- **Azure's zone binding.** Unlike Cloudflare, `AzureProvider.apply` passes `record.zone` into every SDK call (azure.py:76, 80), so it cannot write into a zone the record does not claim. That is the pattern CR-4 asks Cloudflare to adopt.

---

### Independently corroborated by the adversarial pass

The second pass ran its own attacks on the allowlist and reported `protected records touched: NONE` across eight configurations: a record literally named `demo.dwsolution.co.dwsolution.co` while `demo` was managed; `www A` + `external-check TXT` + a same-name-different-type `reconciler-check A` while `reconciler-check TXT` was managed; an apex `A` while apex `TXT` was managed; config and snapshot with trailing dots and mixed case throughout (`"DWSolution.CO."` / `"DEMO."` / `"cname"`); the same zone declared twice with different case and disjoint key sets; and a snapshot carrying an unowned `www A` plus a foreign-zone record (both ignored, neither written). Across all seven truth-failure scenarios — including totally empty truth — the Terraform seeds `www`, `external-check`, and `db` survived untouched every time.

It also confirmed two properties worth stating positively: **partial-apply retries do not compound.** A Cloudflare `to_update` whose creates succeeded and whose DELETE hit a 500 left the RRset over-serving and exited 1; the retry re-planned from a fresh fetch and converged cleanly with no double-create and no orphan. Create-before-delete means the failure window over-serves rather than under-serves — the right trade for availability (and the reason CR-2 is specifically a CNAME problem, not a general ordering bug). **Idempotency holds for 10 of 13 value shapes**, including CNAME case/trailing-dot, non-canonical IPv6, reordered multi-value A, Cloudflare `ttl:1` auto, and the apex `@` key; the three failures are all TXT-specific and trace to `_content`/`_match_key` not being inverses of `_create` and `model._canonical_value` (WR-6, WR-13).

---

_Reviewed: 2026-08-06_
_Reviewers: Claude — primary deep review (gsd-code-reviewer) + independent adversarial mutation-path audit; findings merged_
_Depth: deep_
_Reproductions: 23 probes run against the checked-out tree via `uv run python` with `responses`-mocked HTTP and injected SDK fakes; no tracked source file was modified._
