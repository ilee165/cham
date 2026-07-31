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
