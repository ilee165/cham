# Spoke module — reusable VNet with subnets, NSG, UDR to hub, and bidirectional peering.
# Instantiated once per spoke from envs/lab/main.tf with different tfvars.

terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

resource "azurerm_virtual_network" "spoke" {
  #checkov:skip=CKV_AZURE_182:owner=repository-maintainer; exact=azurerm_virtual_network.spoke; rationale=the approved cost-controlled lab intentionally has one hub DNS/NVA VM; control=saved-plan review and destroy/recreate recovery bound the single-node risk.
  #checkov:skip=CKV_AZURE_183:owner=repository-maintainer; exact=azurerm_virtual_network.spoke; rationale=Checkov cannot resolve the module output to its local address; control=dns_servers is wired only to the hub VM static private IP 10.10.0.10.
  name                = "vnet-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = [var.address_space]
  dns_servers         = var.dns_servers # hub BIND9 VM IP — set after hub exists
  tags                = var.tags
}

resource "azurerm_subnet" "subnets" {
  #checkov:skip=CKV2_AZURE_31:owner=repository-maintainer; exact=azurerm_subnet.subnets; rationale=Checkov does not correlate every for_each subnet instance; control=azurerm_subnet_network_security_group_association.spoke attaches the spoke NSG to every subnet instance using the same for_each map.
  for_each             = var.subnets
  name                 = "snet-${each.key}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.spoke.name
  address_prefixes     = [each.value]
}

# --- NSG: spoke-to-spoke is fully denied, including via the hub. The hub NSG
# has no inter-spoke transit allow and the NVA does not SNAT east-west, so
# forwarded inter-spoke packets are dropped at the hub NIC (DenyAllOtherInbound)
# and would hit DenyOtherSpokes here even if forwarded. To permit hub transit
# later: add a hub NSG inbound allow (spoke -> spoke) AND an allow for the
# sibling-spoke CIDR here with a lower priority number than DenyOtherSpokes (200). ---
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
    name                       = "AllowWireGuardTransfer"
    priority                   = 111
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = var.wg_transfer_cidr
    destination_address_prefix = "*"
  }

  # NEW-IN-04 (2026-08-10 review): previously denied the hardcoded
  # 10.10.0.0/16 supernet, so a spoke configured outside it was not covered.
  # Denying the configured spoke list keeps the rule aligned with whatever
  # CIDRs the caller actually deploys. Traffic from this spoke's own space is
  # still admitted by AllowIntraSpoke (priority 150) before this rule fires.
  security_rule {
    name                       = "DenyOtherSpokes"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefixes    = var.spoke_address_spaces
    destination_address_prefix = "*"
  }
  # DenyOtherSpokes runs before Azure's default AllowVnetInBound rule. Explicit
  # hub, on-prem, transfer-network, and intra-spoke allows remain authoritative.

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
#
# Both peerings wait on every write that touches a subnet of THIS VNet, for the
# same reason the hub's vnet_id/vnet_name outputs wait on the hub's subnets: a
# subnet write leaves its VNet in `Updating` for some seconds after the subnet
# resource itself reports success, and a peering referencing a VNet in that
# state is rejected with `ReferencedResourceNotProvisioned`. Referencing
# `azurerm_virtual_network.spoke` only creates an edge on the VNet existing.
#
# Both directions need it, not just the one that failed: spoke_to_hub is created
# ON this VNet, and hub_to_spoke names it as the remote. Azure requires both
# ends to be in Succeeded state.
resource "azurerm_virtual_network_peering" "spoke_to_hub" {
  name                      = "peer-${var.name}-to-hub"
  resource_group_name       = var.resource_group_name
  virtual_network_name      = azurerm_virtual_network.spoke.name
  remote_virtual_network_id = var.hub_vnet_id

  allow_virtual_network_access = true
  allow_forwarded_traffic      = true # REQUIRED for on-prem traffic arriving via hub NVA
  use_remote_gateways          = false

  depends_on = [
    azurerm_subnet.subnets,
    azurerm_subnet_network_security_group_association.spoke,
    azurerm_subnet_route_table_association.spoke,
  ]
}

resource "azurerm_virtual_network_peering" "hub_to_spoke" {
  name                      = "peer-hub-to-${var.name}"
  resource_group_name       = var.resource_group_name
  virtual_network_name      = var.hub_vnet_name
  remote_virtual_network_id = azurerm_virtual_network.spoke.id

  allow_virtual_network_access = true
  allow_forwarded_traffic      = true
  allow_gateway_transit        = false

  depends_on = [
    azurerm_subnet.subnets,
    azurerm_subnet_network_security_group_association.spoke,
    azurerm_subnet_route_table_association.spoke,
  ]
}
