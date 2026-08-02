# Hub module — hub VNet plus the B1s VM running WireGuard + BIND9.
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

  security_rule {
    name                       = "AllowWireGuardFromHome"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = "51820"
    source_address_prefix      = var.home_ip # /32 — never widen this
    destination_address_prefix = "*"
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
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowDNSFromRFC1918"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_ranges    = ["53"]
    source_address_prefixes    = ["10.10.0.0/16", var.onprem_address_space, var.wg_transfer_cidr]
    destination_address_prefix = "*"
  }

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

# --- The B1s VM (cost-bearing; review current subscription pricing before apply) ---
resource "azurerm_linux_virtual_machine" "hub" {
  name                       = "vm-hub-ddi"
  location                   = var.location
  resource_group_name        = var.resource_group_name
  size                       = "Standard_B1s"
  admin_username             = var.admin_username
  allow_extension_operations = false
  network_interface_ids      = [azurerm_network_interface.hub.id]
  tags                       = var.tags

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
    version   = "latest"
  }

  custom_data = base64encode(templatefile("${path.module}/cloud-init.yml.tpl", {
    onprem_cidr        = var.onprem_address_space
    wg_transfer_cidr   = var.wg_transfer_cidr
    lab_zone           = var.lab_zone
    onprem_dns_ip      = var.onprem_dns_ip # laptop BIND9 via tunnel
    wg_peer_public_key = var.wg_peer_public_key
  }))
}
