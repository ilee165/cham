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
}

module "hub" {
  source                       = "../../modules/hub"
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
  forwarding_vnet_links = {
    hub  = module.hub.vnet_id
    app  = module.spoke_app.vnet_id
    mgmt = module.spoke_mgmt.vnet_id
  }
  lab_zone   = var.lab_zone
  hub_dns_ip = module.hub.vm_private_ip
  tags       = local.tags
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
