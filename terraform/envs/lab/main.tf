locals {
  tags = {
    project = "cham-lab"
    managed = "terraform"
    env     = "lab"
  }

  # Single source of truth for spoke CIDRs — consumed by the hub NSG transit
  # allow-list AND each spoke's address_space so they cannot drift. Editing a
  # spoke CIDR in only one place used to cause a silent full-egress outage
  # for that spoke (hub DenyAllOtherInbound). Note: values() sorts by key.
  spoke_cidrs = {
    app  = "10.10.4.0/22"
    mgmt = "10.10.8.0/22"
  }

  # Keep resolver addressing single-sourced because the hub NSG must permit
  # tunnel-originated DNS traffic to the same inbound subnet the managed
  # resolver uses when the cost-gated feature is enabled.
  resolver_inbound_subnet_cidr  = "10.10.2.0/28"
  resolver_outbound_subnet_cidr = "10.10.2.16/28"

  # WR-06: mirror of the hub module's address_space, held here and passed
  # explicitly so the root can prove the routed networks below are pairwise
  # disjoint — the module default alone would leave the root reasoning about
  # a value it never sees.
  hub_address_space = "10.10.0.0/22"

  # Every top-level routed network. These meet in UDRs, NSG rules, BIND ACLs,
  # WireGuard AllowedIPs, and NAT sources; an overlap plans cleanly and then
  # hairpins or blackholes traffic depending on which table wins.
  routed_networks = {
    hub                = local.hub_address_space
    spoke_app          = local.spoke_cidrs.app
    spoke_mgmt         = local.spoke_cidrs.mgmt
    onprem             = var.onprem_address_space
    wireguard_transfer = var.wg_transfer_cidr
  }

  # Two CIDRs overlap iff, at the coarser of the two prefix lengths, both
  # networks collapse to the same address. try() defaults to true so a
  # malformed operand reads as a collision (fail closed) — the per-variable
  # syntax validations then name the actual problem.
  # HCL's < compares only numbers, so pair up by index rather than by name;
  # objects (not tuples) survive flatten(), which recurses into nested lists.
  routed_network_names = keys(local.routed_networks)
  routed_network_pairs = flatten([
    for i, a in local.routed_network_names : [
      for j, b in local.routed_network_names : { a = a, b = b } if i < j
    ]
  ])

  routed_network_overlaps = [
    for pair in local.routed_network_pairs :
    format("%s (%s) overlaps %s (%s)",
      pair.a, local.routed_networks[pair.a],
      pair.b, local.routed_networks[pair.b],
    )
    if try(
      cidrsubnet(format("%s/%d", split("/", local.routed_networks[pair.a])[0], min(
        tonumber(split("/", local.routed_networks[pair.a])[1]),
        tonumber(split("/", local.routed_networks[pair.b])[1]),
      )), 0, 0)
      == cidrsubnet(format("%s/%d", split("/", local.routed_networks[pair.b])[0], min(
        tonumber(split("/", local.routed_networks[pair.a])[1]),
        tonumber(split("/", local.routed_networks[pair.b])[1]),
      )), 0, 0),
    true)
  ]

  # Per-spoke overrides can represent the quota-blocked app-only live state.
  # The legacy shared flag remains a compatibility fallback for existing
  # gitignored tfvars and must not be used for new configuration.
  test_vm_enabled = {
    app  = var.enable_test_vm_app != null ? var.enable_test_vm_app : var.enable_test_vm
    mgmt = var.enable_test_vm_mgmt != null ? var.enable_test_vm_mgmt : var.enable_test_vm
  }
  test_nic_enabled = {
    app  = var.enable_test_nic_app != null ? var.enable_test_nic_app : local.test_vm_enabled.app
    mgmt = var.enable_test_nic_mgmt != null ? var.enable_test_nic_mgmt : local.test_vm_enabled.mgmt
  }
}

resource "azurerm_resource_group" "lab" {
  name     = "rg-cham-lab"
  location = var.location
  tags     = local.tags

  # WR-06: every other resource depends on this group, so a routed-network
  # overlap stops the whole plan here, before anything is created.
  lifecycle {
    precondition {
      condition     = length(local.routed_network_overlaps) == 0
      error_message = "Top-level routed networks must be pairwise disjoint — an overlap plans cleanly and then hairpins or blackholes traffic at runtime: ${join("; ", local.routed_network_overlaps)}"
    }
  }
}

module "hub" {
  source                       = "../../modules/hub"
  address_space                = local.hub_address_space
  location                     = var.location
  vm_size                      = var.vm_size
  disk_controller_type         = var.hub_disk_controller_type
  resource_group_name          = azurerm_resource_group.lab.name
  home_ip                      = var.home_ip
  ssh_public_key               = var.ssh_public_key
  lab_zone                     = var.lab_zone
  onprem_dns_ip                = var.onprem_dns_ip
  onprem_address_space         = var.onprem_address_space
  spoke_address_spaces         = values(local.spoke_cidrs)
  wg_transfer_cidr             = var.wg_transfer_cidr
  enable_private_resolver      = var.enable_private_resolver
  resolver_inbound_subnet_cidr = local.resolver_inbound_subnet_cidr
  wg_peer_public_key           = var.wg_peer_public_key
  tags                         = local.tags
}

# Same module, two instantiations — the reusability story.
module "spoke_app" {
  source               = "../../modules/spoke"
  name                 = "app"
  location             = var.location
  vm_size              = var.test_vm_size
  disk_controller_type = var.test_vm_disk_controller_type
  resource_group_name  = azurerm_resource_group.lab.name
  address_space        = local.spoke_cidrs.app
  subnets              = { workload = "10.10.4.0/24" }
  dns_servers          = [module.hub.vm_private_ip]
  hub_vnet_id          = module.hub.vnet_id
  hub_vnet_name        = module.hub.vnet_name
  hub_address_space    = module.hub.vnet_address_space
  hub_nva_ip           = module.hub.vm_private_ip
  spoke_address_spaces = values(local.spoke_cidrs)
  onprem_address_space = var.onprem_address_space
  wg_transfer_cidr     = var.wg_transfer_cidr
  enable_test_vm       = local.test_vm_enabled.app
  enable_test_nic      = local.test_nic_enabled.app
  ssh_public_key       = var.ssh_public_key
  tags                 = local.tags
}

module "spoke_mgmt" {
  source               = "../../modules/spoke"
  name                 = "mgmt"
  location             = var.location
  vm_size              = var.test_vm_size
  disk_controller_type = var.test_vm_disk_controller_type
  resource_group_name  = azurerm_resource_group.lab.name
  address_space        = local.spoke_cidrs.mgmt
  subnets              = { tools = "10.10.8.0/24" }
  dns_servers          = [module.hub.vm_private_ip]
  hub_vnet_id          = module.hub.vnet_id
  hub_vnet_name        = module.hub.vnet_name
  hub_address_space    = module.hub.vnet_address_space
  hub_nva_ip           = module.hub.vm_private_ip
  spoke_address_spaces = values(local.spoke_cidrs)
  onprem_address_space = var.onprem_address_space
  wg_transfer_cidr     = var.wg_transfer_cidr
  enable_test_vm       = local.test_vm_enabled.mgmt
  enable_test_nic      = local.test_nic_enabled.mgmt
  ssh_public_key       = var.ssh_public_key
  tags                 = local.tags

  # Sequence the spoke creates so regional-core evaluation is deterministic:
  # the app VM is committed before Azure evaluates the management VM, which
  # keeps quota errors attributable to a single resource instead of a race.
  depends_on = [module.spoke_app]
}

module "private_dns" {
  source              = "../../modules/private-dns"
  zone_name           = "azure.${var.public_zone}"
  resource_group_name = azurerm_resource_group.lab.name
  vnet_links = {
    hub  = { vnet_id = module.hub.vnet_id, registration = false }
    app  = { vnet_id = module.spoke_app.vnet_id, registration = true }
    mgmt = { vnet_id = module.spoke_mgmt.vnet_id, registration = true }
  }
  a_records = {
    # Terraform owns seed records; the reconciler owns a disjoint managed set.
    "db" = "10.10.4.20"
  }
  tags = local.tags
}

# FLAG-GATED — see modules/dns-resolver/main.tf cost warning
module "dns_resolver" {
  source               = "../../modules/dns-resolver"
  enabled              = var.enable_private_resolver
  location             = var.location
  resource_group_name  = azurerm_resource_group.lab.name
  hub_vnet_id          = module.hub.vnet_id
  hub_vnet_name        = module.hub.vnet_name
  hub_nva_ip           = module.hub.vm_private_ip
  onprem_address_space = var.onprem_address_space
  wg_transfer_cidr     = var.wg_transfer_cidr
  inbound_subnet_cidr  = local.resolver_inbound_subnet_cidr
  outbound_subnet_cidr = local.resolver_outbound_subnet_cidr
  # WR-06: the module proves both resolver subnets fit the hub range and miss
  # the subnets the hub has already carved.
  hub_address_space         = module.hub.vnet_address_space
  hub_reserved_subnet_cidrs = [module.hub.vpn_subnet_cidr, module.hub.shared_subnet_cidr]
  forwarding_vnet_links = {
    hub  = module.hub.vnet_id
    app  = module.spoke_app.vnet_id
    mgmt = module.spoke_mgmt.vnet_id
  }
  lab_zone   = var.lab_zone
  hub_dns_ip = module.hub.vm_private_ip
  tags       = local.tags

  # CR-07: the forwarding VNet links reference the spoke VNets, not their
  # hub-side peerings, so without this the resolver can be provisioned while
  # a peering is still in flight — the ReferencedResourceNotProvisioned class
  # that already hit the spoke pair (PR #13). Serialize after both spokes.
  depends_on = [module.spoke_app, module.spoke_mgmt]
}

# Budget alert — notification only. Azure has NO automatic spend cap.
# The real kill switch is .github/workflows/destroy.yml.
resource "azurerm_consumption_budget_subscription" "lab" {
  name            = "budget-cham-lab"
  subscription_id = "/subscriptions/${var.subscription_id}"
  amount          = var.budget_amount
  time_grain      = "Monthly"

  time_period {
    start_date = var.budget_start_date # first of current month, RFC3339
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 90
    operator       = "GreaterThan"
    contact_emails = [var.alert_email]
  }
}
