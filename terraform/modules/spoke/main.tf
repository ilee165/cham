# Spoke module — reusable VNet with subnets, NSG, UDR to hub, and bidirectional peering.
# Instantiated once per spoke from envs/lab/main.tf with different tfvars.

resource "azurerm_virtual_network" "spoke" {
  name                = "vnet-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = [var.address_space]
  dns_servers         = var.dns_servers # hub BIND9 VM IP — set after hub exists
  tags                = var.tags
}

resource "azurerm_subnet" "subnets" {
  for_each             = var.subnets
  name                 = "snet-${each.key}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = [each.value]
}

# --- NSG: deny spoke-to-spoke direct, allow via hub only ---
resource "azurerm_network_security_group" "spoke" {
  name                = "nsg-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  security_rule {
    name                       = "AllowFromHub"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = var.hub_address_space
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowOnPrem"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = var.onprem_address_space
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "DenyOtherSpokes"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "10.10.0.0/16" # whole Azure supernet
    destination_address_prefix = "*"
  }
  # Default rules still allow VirtualNetwork after 200? No — priority 200 Deny
  # fires before the default AllowVnetInBound (65000). Intra-spoke traffic is
  # covered because it never leaves the VNet... it does hit the NSG. See
  # AllowIntraSpoke below.

  security_rule {
    name                       = "AllowIntraSpoke"
    priority                   = 150
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = var.address_space
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "spoke" {
  for_each                  = azurerm_subnet.subnets
  subnet_id                 = each.value.id
  network_security_group_id = azurerm_network_security_group.spoke.id
}

# --- UDR: default route through hub NVA (BIND9/WireGuard VM) ---
resource "azurerm_route_table" "spoke" {
  name                = "rt-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  route {
    name                   = "default-via-hub"
    address_prefix         = "0.0.0.0/0"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.hub_nva_ip
  }

  route {
    name                   = "onprem-via-hub"
    address_prefix         = var.onprem_address_space
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = var.hub_nva_ip
  }
}

resource "azurerm_subnet_route_table_association" "spoke" {
  for_each       = azurerm_subnet.subnets
  subnet_id      = each.value.id
  route_table_id = azurerm_route_table.spoke.id
}

# --- Peering, both directions ---
resource "azurerm_virtual_network_peering" "spoke_to_hub" {
  name                      = "peer-${var.name}-to-hub"
  resource_group_name       = var.resource_group_name
  virtual_network_name      = azurerm_virtual_network.spoke.name
  remote_virtual_network_id = var.hub_vnet_id

  allow_virtual_network_access = true
  allow_forwarded_traffic      = true # REQUIRED for on-prem traffic arriving via hub NVA
  use_remote_gateways          = false
}

resource "azurerm_virtual_network_peering" "hub_to_spoke" {
  name                      = "peer-hub-to-${var.name}"
  resource_group_name       = var.resource_group_name
  virtual_network_name      = var.hub_vnet_name
  remote_virtual_network_id = azurerm_virtual_network.spoke.id

  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  allow_gateway_transit        = false
}
