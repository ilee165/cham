output "inbound_endpoint_ip" {
  value = var.enabled ? azurerm_private_dns_resolver_inbound_endpoint.inbound[0].ip_configurations[0].private_ip_address : null
}
