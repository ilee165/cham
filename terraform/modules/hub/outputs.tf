output "vnet_id" { value = azurerm_virtual_network.hub.id }
output "vnet_name" { value = azurerm_virtual_network.hub.name }
output "vnet_address_space" { value = var.address_space }
output "vm_private_ip" { value = var.hub_vm_ip }
output "vm_public_ip" { value = azurerm_public_ip.hub.ip_address }
output "shared_subnet_id" { value = azurerm_subnet.shared.id }
