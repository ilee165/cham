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
