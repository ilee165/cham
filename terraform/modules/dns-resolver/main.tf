# Azure DNS Private Resolver — FLAG-GATED. count = 0 unless explicitly enabled.
#
#   COST: ~$180/mo PER endpoint, prorated hourly. Both endpoints for a month
#   would consume nearly the entire $200 trial credit. Enable for a single
#   session, screenshot, disable, apply. Set a phone timer.
#
# Subnets must be /28+, delegated to Microsoft.Network/dnsResolvers, and
# usable for nothing else.

resource "azurerm_subnet" "resolver_inbound" {
  count                = var.enabled ? 1 : 0
  name                 = "snet-resolver-in"
  resource_group_name  = var.resource_group_name
  virtual_network_name = var.hub_vnet_name
  address_prefixes     = [var.inbound_subnet_cidr]

  delegation {
    name = "resolver"
    service_delegation {
      name    = "Microsoft.Network/dnsResolvers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "resolver_outbound" {
  count                = var.enabled ? 1 : 0
  name                 = "snet-resolver-out"
  resource_group_name  = var.resource_group_name
  virtual_network_name = var.hub_vnet_name
  address_prefixes     = [var.outbound_subnet_cidr]

  delegation {
    name = "resolver"
    service_delegation {
      name    = "Microsoft.Network/dnsResolvers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_resolver" "resolver" {
  count               = var.enabled ? 1 : 0
  name                = "dnspr-hub"
  location            = var.location
  resource_group_name = var.resource_group_name
  virtual_network_id  = var.hub_vnet_id
}

resource "azurerm_private_dns_resolver_inbound_endpoint" "inbound" {
  count                   = var.enabled ? 1 : 0
  name                    = "in-endpoint"
  location                = var.location
  private_dns_resolver_id = azurerm_private_dns_resolver.resolver[0].id

  ip_configurations {
    subnet_id = azurerm_subnet.resolver_inbound[0].id
  }
}

resource "azurerm_private_dns_resolver_outbound_endpoint" "outbound" {
  count                   = var.enabled ? 1 : 0
  name                    = "out-endpoint"
  location                = var.location
  private_dns_resolver_id = azurerm_private_dns_resolver.resolver[0].id
  subnet_id               = azurerm_subnet.resolver_outbound[0].id
}

resource "azurerm_private_dns_resolver_dns_forwarding_ruleset" "ruleset" {
  count                                      = var.enabled ? 1 : 0
  name                                       = "ruleset-lab"
  location                                   = var.location
  resource_group_name                        = var.resource_group_name
  private_dns_resolver_outbound_endpoint_ids = [azurerm_private_dns_resolver_outbound_endpoint.outbound[0].id]
}

resource "azurerm_private_dns_resolver_forwarding_rule" "lab" {
  count                     = var.enabled ? 1 : 0
  name                      = "lab-zone"
  dns_forwarding_ruleset_id = azurerm_private_dns_resolver_dns_forwarding_ruleset.ruleset[0].id
  domain_name               = "${var.lab_zone}." # trailing dot required
  enabled                   = true

  target_dns_servers {
    ip_address = var.onprem_dns_ip
    port       = 53
  }
}
