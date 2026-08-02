output "vnet_id" {
  value = azurerm_virtual_network.spoke.id
}

output "vnet_name" {
  value = azurerm_virtual_network.spoke.name
}

output "subnet_ids" {
  value = { for k, s in azurerm_subnet.subnets : k => s.id }
}

output "testvm_private_ip" {
  description = "Private IP of the verification VM, or null when disabled."
  value       = try(azurerm_network_interface.testvm[0].private_ip_address, null)
}
