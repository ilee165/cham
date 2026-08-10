# Architecture Decision Records

Short ADRs. Format: context → decision → tradeoff accepted. These are
interview material as much as documentation.

## ADR-001: BIND9 on a burstable VM instead of Azure DNS Private Resolver
- **Context:** Hybrid resolution needs a forwarder in the hub. Private
  Resolver is the managed answer at ~$180/mo per endpoint (~$360 both ways);
  a small VM used only during bounded lab sessions has materially lower cost.
- **Decision:** BIND9 on a parameterized small hub VM; Private Resolver
  remains flag-gated. No free-service entitlement is assumed.
- **Amended 2026-08-03:** the original B2ats v2 / North Central US sizing is
  superseded. NCUS could not supply six regional cores (terminal
  `ResourceNotAvailableForOffer`) nor any usable one-vCPU SKU, and this
  subscription gets no x86 B-family SKU in any probed region. The lab now
  runs in East US 2 on NVMe-only v7 sizes — `Standard_D2als_v7` hub,
  `Standard_F1als_v7` test VMs (evidence: `docs/evidence/phase2/`). The
  core decision — BIND9 on a VM instead of the managed resolver — is
  unchanged.
- **Tradeoff accepted:** we own patching, HA (none — single VM), and zone
  redundancy that the managed service would provide. Right call at lab
  scale. The flag provisions a testable managed resolver path, but the current
  spokes keep using custom DNS on the hub VM; a production cutover must also
  move clients to Azure-provided DNS (or otherwise redirect their DNS path).

## ADR-002: WireGuard instead of Azure VPN Gateway
- **Context:** Site-to-site tunnel laptop↔Azure. VPN Gateway Basic ~$29/mo,
  VpnGw1 ~$140/mo; gateway provisioning alone takes ~30-45 min.
- **Decision:** WireGuard on the hub VM. Free, instant, and demonstrates
  the tunnel + routing + NSG work explicitly rather than as a managed box.
- **Tradeoff accepted:** no BGP over the tunnel, no managed SLA, manual key
  handling. IPsec/IKEv2 knowledge still applies conceptually.

## ADR-003: Hub-and-spoke over a single flat VNet
- **Context:** One VNet would work at this scale.
- **Decision:** Hub + two spokes with peering, NSG isolation, and UDRs
  through the hub NVA.
- **Tradeoff accepted:** more moving parts than the lab strictly needs —
  deliberately, because the topology *is* the demonstration (Subaru/ESRT).

## ADR-004: Separate Terraform state for Cloudflare vs Azure
- **Context:** One state file is simpler.
- **Decision:** Split state (lab.tfstate / cloudflare.tfstate), shared
  backend storage account.
- **Tradeoff accepted:** two inits, two plans. In exchange: independent
  blast radius, independent credentials, and a public-zone mistake can't
  hold the Azure stack's lock.

## ADR-005: SpatiumDDI as source of truth; Terraform seeds, reconciler converges
- **Context:** Two writers (Terraform, reconciler) to the same DNS zones
  invites ownership fights.
- **Decision:** Terraform owns infrastructure + seed records. SpatiumDDI is
  the record-level source of truth. The reconciler converges edges toward
  it and NEVER touches records outside its managed set (e.g. Azure
  auto-registration records).
- **Tradeoff accepted:** a record's origin (seed vs reconciled) requires
  knowing the convention. Documented here; enforced by managed zones plus
  an explicit canonical record-key allowlist. Deletion is impossible without
  a key in that allowlist.

## ADR-006: CI drift detection compares edges to a committed desired-state snapshot
- **Context:** Nightly CI cannot reach the laptop's SpatiumDDI API (home NAT,
  stack usually down), but edge drift is exactly what CI should catch.
- **Decision:** Sessions end with `cham-reconcile --export desired-records.json`
  (committed). Nightly drift runs
  `cham-reconcile --dry-run --desired-from-file desired-records.json` and keys
  off the exit code (0 converged / 2 drift / 1 error).
- **Amended 2026-08-08 (scope of the scheduled run):** the live workflow
  deliberately checks **only the public edge**
  (`--dry-run --edge cloudflare-public`), with the read-only token and no
  Azure credentials. The Azure lab is destroyed between sessions for cost
  control, so an unattended two-edge run would fail every night on a resource
  group that is absent by design — and a permanently red job detects nothing.
  The Azure edge is checked by hand during live sessions; extending the
  schedule to gate on lab presence is Phase 5 work.
- **Amended 2026-08-10 (Phase 5 — presence-gated, not excluded):** the
  scheduled run now asks Azure whether `rg-cham-lab` exists and builds its
  `--edge` list from the answer: `cloudflare-public` always,
  `azure-private` only when the lab is up. The workflow is therefore correct
  in both states with no edit when the lab comes and goes, and the "between
  sessions the Azure edge is unmonitored" tradeoff below now reads as
  "unmonitored only while it does not exist". An indeterminate answer from
  `az group exists` is a hard failure rather than an assumed `false`, so a
  broken credential can never masquerade as a converged public-only night.
  The read-only Cloudflare token is unchanged — the unattended job still
  cannot mutate DNS.
- The operational
  procedure — export at session end, snapshot diff review, drift-issue
  healing — lives in the runbook's "Reconciler snapshot + drift operations"
  section. CI additionally rejects a committed snapshot whose
  `truth_verified` flag is false, so an unprovable read cannot become the
  standing truth the nightly job acts on.
- **Tradeoff accepted:** The snapshot can lag live truth between sessions, so
  CI detects "edge vs last-exported truth". Acceptable: truth only changes
  during sessions, and sessions end with an export. Between sessions the
  Azure edge is unmonitored; accepted because the edge does not exist then.

## ADR-007: The `www` split horizon lives on the SpatiumDDI resolver, not the hub
- **Context:** Two independent BIND9 instances serve this lab. The hub's is
  configured by cloud-init and is what a tunnel client reaches at
  `10.10.0.10`; the SpatiumDDI-managed one runs as an agent container and is
  what the control plane renders zones onto. Task A3 created the
  `www.dwsolution.co` single-name override zone on the SpatiumDDI side only,
  so the hub still answers `www` with the public GitHub Pages addresses.
- **Decision:** Record the split as it actually stands rather than paper over
  it. The split horizon is proven and real for clients querying the
  SpatiumDDI resolver; it does not apply to clients using the hub's resolver.
  Unifying them is deferred to Phase 5.
- **Options when it is taken up:** register the hub's BIND9 as a server in the
  SpatiumDDI `primary` group, so the control plane owns hub DNS and renders
  the override there (consistent with ADR-005 — one source of truth); or add
  the override zone to the hub's cloud-init, which is simpler but gives hub
  DNS two owners and reintroduces exactly the ownership fight ADR-005 exists
  to prevent. The first is preferred.
- **Tradeoff accepted:** until then, "the split horizon works" is a claim that
  needs the resolver named. Evidence in
  `docs/evidence/phase4/split-horizon.txt` states which resolver was queried
  for every measurement.
