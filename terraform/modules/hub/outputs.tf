# The two identifiers below are consumed by the spoke module to build peerings,
# and both are gated on every write that touches a subnet of this VNet.
#
# Azure returns the VNet's id and name as soon as the VNet itself exists, while
# adding or associating a subnet leaves the VNet in `Updating` for some seconds
# afterwards. A peering created against a VNet in that state is rejected —
# `ReferencedResourceNotProvisioned ... the last operation that updated/is
# updating the resource is PutSubnetOperation` — and because Terraform's only
# edge here is "the VNet exists", nothing in the graph prevents the race. It is
# timing-dependent, so it fails intermittently rather than reliably: it took
# down Checkpoint B on 2026-08-03 and the first Phase 5 lab apply
# (run 31603340729) on 2026-08-12.
#
# depends_on on an output propagates to whatever consumes it, so gating the ids
# is enough — the consumer waits without the spoke module needing to know why,
# and the hub VM (which no peering references) still builds in parallel.
output "vnet_id" {
  value = azurerm_virtual_network.hub.id
  depends_on = [
    azurerm_subnet.shared,
    azurerm_subnet.vpn,
    azurerm_subnet_network_security_group_association.shared,
    azurerm_subnet_network_security_group_association.vpn,
  ]
}

output "vnet_name" {
  value = azurerm_virtual_network.hub.name
  depends_on = [
    azurerm_subnet.shared,
    azurerm_subnet.vpn,
    azurerm_subnet_network_security_group_association.shared,
    azurerm_subnet_network_security_group_association.vpn,
  ]
}
output "vnet_address_space" { value = var.address_space }

# WR-06: consumed by the root to tell the dns-resolver module which hub
# subnets its inbound/outbound subnets must not collide with.
output "vpn_subnet_cidr" { value = var.vpn_subnet_cidr }
output "shared_subnet_cidr" { value = var.shared_subnet_cidr }
output "vm_private_ip" { value = var.hub_vm_ip }
output "vm_public_ip" { value = azurerm_public_ip.hub.ip_address }
output "shared_subnet_id" { value = azurerm_subnet.shared.id }
