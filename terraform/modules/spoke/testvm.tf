locals {
  # Explicit subnet selection for the test VM. values(...)[0] picked whichever
  # subnet key sorts first alphabetically — adding an earlier-sorting subnet
  # (e.g. "bastion" before "workload") would silently re-home the NIC and force
  # NIC/VM replacement. one() instead fails at plan time when the map grows
  # beyond one subnet and no explicit test_vm_subnet_key was chosen.
  test_vm_subnet_key = var.test_vm_subnet_key != null ? var.test_vm_subnet_key : one(keys(var.subnets))
}

resource "azurerm_network_interface" "testvm" {
  count               = var.enable_test_vm ? 1 : 0
  name                = "nic-testvm-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.subnets[local.test_vm_subnet_key].id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "testvm" {
  count                      = var.enable_test_vm ? 1 : 0
  name                       = "vm-test-${var.name}"
  location                   = var.location
  resource_group_name        = var.resource_group_name
  size                       = var.vm_size
  admin_username             = var.admin_username
  allow_extension_operations = false
  network_interface_ids      = [azurerm_network_interface.testvm[0].id]
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
}
