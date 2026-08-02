output "hub_public_ip" {
  description = "WireGuard endpoint — point the laptop peer here"
  value       = module.hub.vm_public_ip
}

output "hub_private_ip" {
  description = "VNet DNS server / UDR next-hop"
  value       = module.hub.vm_private_ip
}

output "resolver_inbound_ip" {
  description = "Only populated during a Private Resolver session"
  value       = module.dns_resolver.inbound_endpoint_ip
}

output "testvm_app_ip" {
  description = "Private IP of the app verification VM, or null when disabled."
  value       = module.spoke_app.testvm_private_ip
}

output "testvm_mgmt_ip" {
  description = "Private IP of the management verification VM, or null when disabled."
  value       = module.spoke_mgmt.testvm_private_ip
}
