# Hub module — hub VNet plus the burstable VM running WireGuard + BIND9.
# This VM is the NVA: spokes route through it, and it forwards DNS
# conditionally to on-prem (lab zone) or Azure-provided DNS (everything else).

terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# WR-02 (2026-08-08 review): every "internal lab space" consumer — DNS/HTTP
# NSG sources, the BIND ACL, and NAT source matching — derives from the module
# inputs. Previously these hard-coded 10.10.0.0/16, so a caller supplying
# spokes outside that aggregate got transit rules that followed the variable
# while DNS access and Internet NAT silently did not.
locals {
  internal_cidrs = concat([var.address_space], var.spoke_address_spaces)
}

resource "azurerm_virtual_network" "hub" {
  name                = "vnet-hub"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = [var.address_space]
  tags                = var.tags
}

resource "azurerm_subnet" "vpn" {
  name                 = "snet-vpn"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.vpn_subnet_cidr]
}

resource "azurerm_subnet" "shared" {
  name                 = "snet-shared"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = [var.shared_subnet_cidr]
}

# --- Public IP for the WireGuard endpoint ---
resource "azurerm_public_ip" "hub" {
  name                = "pip-hub-ddi"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

# --- NSG: WireGuard from home IP ONLY. SSH from home IP only. ---
resource "azurerm_network_security_group" "hub" {
  name                = "nsg-hub"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  # Rules 100-120 are destination-scoped to the hub VM, not "*": this NSG is
  # associated to BOTH hub subnets, so a wildcard destination would silently
  # extend SSH/WireGuard/DNS exposure to anything later placed in snet-shared.
  # (NSGs evaluate after DNAT, so traffic to the public IP matches the
  # private hub_vm_ip here.)
  security_rule {
    name                       = "AllowWireGuardFromHome"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = "51820"
    source_address_prefix      = var.home_ip # /32 — never widen this
    destination_address_prefix = var.hub_vm_ip
  }

  security_rule {
    name                       = "AllowSSHFromHome"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.home_ip
    destination_address_prefix = var.hub_vm_ip
  }

  security_rule {
    name                       = "AllowDNSFromRFC1918"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_ranges    = ["53"]
    source_address_prefixes    = concat(local.internal_cidrs, [var.onprem_address_space, var.wg_transfer_cidr])
    destination_address_prefix = var.hub_vm_ip
  }

  # Priority 125, not 130: 130 is already taken by AllowInternetTransitFromSpokes
  # below (Inbound priorities must be unique within an NSG). Placed directly
  # after the DNS rule so the two "internal service on the hub" allows sit
  # together as one block, ahead of the spoke-transit rules that follow.
  #
  # Destination is var.hub_vm_ip, not "*" — see the NSG-scoping invariant
  # above. Source prefixes reuse the same variables as AllowDNSFromRFC1918
  # so this rule cannot silently diverge from it if onprem_address_space or
  # wg_transfer_cidr is overridden.
  security_rule {
    name                       = "AllowHTTPInternal"
    priority                   = 125
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefixes    = concat(local.internal_cidrs, [var.onprem_address_space, var.wg_transfer_cidr])
    destination_address_prefix = var.hub_vm_ip
  }

  security_rule {
    name                       = "AllowInternetTransitFromSpokes"
    priority                   = 130
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefixes    = var.spoke_address_spaces
    destination_address_prefix = "Internet"
  }

  # Explicit allow for spoke -> wg-transfer flows. Without it the return leg
  # of spoke->172.16.x traffic relies on RFC1918 space matching the "Internet"
  # service tag in rule 130, which is undocumented behavior.
  security_rule {
    name                       = "AllowWgTransferTransitFromSpokes"
    priority                   = 135
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefixes    = var.spoke_address_spaces
    destination_address_prefix = var.wg_transfer_cidr
  }

  security_rule {
    name                       = "AllowOnPremTransitFromSpokes"
    priority                   = 140
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefixes    = var.spoke_address_spaces
    destination_address_prefix = var.onprem_address_space
  }

  # ICMP note: ping to the hub VM is INTENTIONALLY blocked. Rules 100-120 are
  # port-scoped (ICMP has no ports, so they never match), rules 130/135/140
  # exclude VNet destinations, and this deny fires before the default
  # AllowVnetInBound — so "DNS works but ping 10.10.0.10 fails" is expected
  # behavior during verification, not an NVA fault. If ping diagnostics are
  # ever wanted, add an Allow with protocol = "Icmp",
  # destination_port_range = "*", sources 10.10.0.0/16 / var.wg_transfer_cidr /
  # var.onprem_address_space, at a priority below 4000.
  security_rule {
    name                       = "DenyAllOtherInbound"
    priority                   = 4000
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # Outbound leg of tunnel-initiated flows (laptop/on-prem -> spoke): after
  # wg0 decapsulation the packet leaves this NIC as a NEW outbound flow whose
  # source (on-prem / wg-transfer space) is outside the VNet, so the default
  # AllowVnetOutBound never matches and DenyAllOutBound (65500) would drop it.
  # Mirrors the inbound transit intent of rules 130/140.
  security_rule {
    name                         = "AllowOutboundForwardedToSpokes"
    priority                     = 130
    direction                    = "Outbound"
    access                       = "Allow"
    protocol                     = "*"
    source_port_range            = "*"
    destination_port_range       = "*"
    source_address_prefixes      = [var.onprem_address_space, var.wg_transfer_cidr]
    destination_address_prefixes = var.spoke_address_spaces
  }

  # The inbound resolver endpoint is reached through this NVA by packets
  # decapsulated from WireGuard. Their source prefixes are not part of the
  # Azure VirtualNetwork service tag, so the default outbound allow does not
  # match. Keep the exception DNS-only and create it only with the paid
  # resolver feature.
  dynamic "security_rule" {
    for_each = var.enable_private_resolver ? [1] : []

    content {
      name                       = "AllowDnsResolverFromTunnel"
      priority                   = 120
      direction                  = "Outbound"
      access                     = "Allow"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_range     = "53"
      source_address_prefixes    = [var.onprem_address_space, var.wg_transfer_cidr]
      destination_address_prefix = var.resolver_inbound_subnet_cidr
    }
  }
}

resource "azurerm_subnet_network_security_group_association" "vpn" {
  subnet_id                 = azurerm_subnet.vpn.id
  network_security_group_id = azurerm_network_security_group.hub.id
}

resource "azurerm_subnet_network_security_group_association" "shared" {
  subnet_id                 = azurerm_subnet.shared.id
  network_security_group_id = azurerm_network_security_group.hub.id
}

# --- NIC with IP forwarding (NVA requirement #1 of 2 — #2 is sysctl in cloud-init) ---
resource "azurerm_network_interface" "hub" {
  #checkov:skip=CKV_AZURE_119:owner=repository-maintainer; exact=azurerm_network_interface.hub; rationale=the hub NIC is the approved WireGuard public endpoint; control=Standard static IP, home-/32 SSH and UDP allows, and a terminal inbound deny restrict exposure.
  name                  = "nic-hub-ddi"
  location              = var.location
  resource_group_name   = var.resource_group_name
  ip_forwarding_enabled = true
  tags                  = var.tags

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.vpn.id
    private_ip_address_allocation = "Static"
    private_ip_address            = var.hub_vm_ip
    public_ip_address_id          = azurerm_public_ip.hub.id
  }
}

# --- Cost-bearing hub VM; review current subscription pricing before apply ---
resource "azurerm_linux_virtual_machine" "hub" {
  name                       = "vm-hub-ddi"
  location                   = var.location
  resource_group_name        = var.resource_group_name
  size                       = var.vm_size
  admin_username             = var.admin_username
  allow_extension_operations = false
  network_interface_ids      = [azurerm_network_interface.hub.id]
  tags                       = var.tags

  disk_controller_type = var.disk_controller_type

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    # WR-05: pinned so a marketplace publish cannot change what a plan
    # deploys. Bump deliberately via PR:
    #   az vm image show --urn Canonical:ubuntu-24_04-lts:server:latest \
    #     --query name -o tsv
    version = "24.04.202608070"
  }

  # Normalize the checked-out template to LF before encoding. Without this,
  # Windows CRLF checkout changes produce a byte-only custom_data diff and
  # force replacement of the hub VM even when every rendered line is equal.
  custom_data = base64encode(replace(templatefile("${path.module}/cloud-init.yml.tpl", {
    onprem_cidr      = var.onprem_address_space
    wg_transfer_cidr = var.wg_transfer_cidr
    # WR-02: hub + spoke CIDRs for the BIND ACL and the NAT script, so
    # DNS access and masquerading follow the same inputs the NSG rules do.
    internal_cidrs = local.internal_cidrs
    # WG interface address derived from wg_transfer_cidr (host .1, same mask)
    # so the tunnel follows the variable instead of a hardcoded 172.16.0.1/24.
    # Renders identically to the old literal under the default CIDR.
    wg_interface_cidr  = "${cidrhost(var.wg_transfer_cidr, 1)}/${split("/", var.wg_transfer_cidr)[1]}"
    lab_zone           = var.lab_zone
    onprem_dns_ip      = var.onprem_dns_ip # laptop BIND9 via tunnel
    wg_peer_public_key = var.wg_peer_public_key
    # nginx binds only this address (see cloud-init nginx site block) so the
    # internal page stays off any interface other than the hub's private IP
    # even if the NSG in this module is ever widened (defense in depth, CR-3).
    hub_vm_ip = var.hub_vm_ip
  }), "\r\n", "\n"))
}
