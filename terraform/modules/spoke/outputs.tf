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
  description = "Private IP of the verification VM, or null when the VM is disabled — even when its NIC is retained, so a quota-blocked or absent VM is never reported as reachable."
  value       = var.enable_test_vm ? try(azurerm_network_interface.testvm[0].private_ip_address, null) : null
}

output "test_nic_private_ip" {
  description = "Private IP of the verification NIC regardless of VM attachment, or null when the NIC is disabled. Use for NIC-level checks on a preserved, VM-less NIC."
  value       = try(azurerm_network_interface.testvm[0].private_ip_address, null)
}
