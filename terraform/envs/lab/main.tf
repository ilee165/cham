locals {
  tags = {
    project = "cham-lab"
    managed = "terraform"
    env     = "lab"
  }
}

resource "azurerm_resource_group" "lab" {
  name     = "rg-cham-lab"
  location = var.location
  tags     = local.tags
}

module "hub" {
  source               = "../../modules/hub"
  location             = var.location
  vm_size              = var.vm_size
  resource_group_name  = azurerm_resource_group.lab.name
  home_ip              = var.home_ip
  ssh_public_key       = var.ssh_public_key
  lab_zone             = var.lab_zone
  onprem_dns_ip        = var.onprem_dns_ip
  onprem_address_space = var.onprem_address_space
  spoke_address_spaces = ["10.10.4.0/22", "10.10.8.0/22"]
  wg_transfer_cidr     = var.wg_transfer_cidr
  wg_peer_public_key   = var.wg_peer_public_key
  tags                 = local.tags
}

# Same module, two instantiations — the reusability story.
module "spoke_app" {
  source               = "../../modules/spoke"
  name                 = "app"
  location             = var.location
  vm_size              = var.test_vm_size
  resource_group_name  = azurerm_resource_group.lab.name
  address_space        = "10.10.4.0/22"
  subnets              = { workload = "10.10.4.0/24" }
  dns_servers          = [module.hub.vm_private_ip]
  hub_vnet_id          = module.hub.vnet_id
  hub_vnet_name        = module.hub.vnet_name
  hub_address_space    = module.hub.vnet_address_space
  hub_nva_ip           = module.hub.vm_private_ip
  onprem_address_space = var.onprem_address_space
  wg_transfer_cidr     = var.wg_transfer_cidr
  enable_test_vm       = var.enable_test_vm
  ssh_public_key       = var.ssh_public_key
  tags                 = local.tags
}

module "spoke_mgmt" {
  source               = "../../modules/spoke"
  name                 = "mgmt"
  location             = var.location
  vm_size              = var.test_vm_size
  resource_group_name  = azurerm_resource_group.lab.name
  address_space        = "10.10.8.0/22"
  subnets              = { tools = "10.10.8.0/24" }
  dns_servers          = [module.hub.vm_private_ip]
  hub_vnet_id          = module.hub.vnet_id
  hub_vnet_name        = module.hub.vnet_name
  hub_address_space    = module.hub.vnet_address_space
  hub_nva_ip           = module.hub.vm_private_ip
  onprem_address_space = var.onprem_address_space
  wg_transfer_cidr     = var.wg_transfer_cidr
  enable_test_vm       = var.enable_test_vm
  ssh_public_key       = var.ssh_public_key
  tags                 = local.tags
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
  source              = "../../modules/dns-resolver"
  enabled             = var.enable_private_resolver
  location            = var.location
  resource_group_name = azurerm_resource_group.lab.name
  hub_vnet_id         = module.hub.vnet_id
  hub_vnet_name       = module.hub.vnet_name
  lab_zone            = var.lab_zone
  hub_dns_ip          = module.hub.vm_private_ip
}

# Budget alert — notification only. Azure has NO automatic spend cap.
# The real kill switch is .github/workflows/destroy.yml.
resource "azurerm_consumption_budget_subscription" "lab" {
  name            = "budget-cham-lab"
  subscription_id = "/subscriptions/${var.subscription_id}"
  amount          = 50
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
