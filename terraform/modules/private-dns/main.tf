# Private DNS zone linked to hub + spokes.
# Auto-registration ON for spokes (VMs self-register), OFF for hub.

resource "azurerm_private_dns_zone" "zone" {
  name                = var.zone_name # e.g. azure.dwsolution.co
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "links" {
  for_each              = var.vnet_links # map: name => { vnet_id, registration }
  name                  = "link-${each.key}"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.zone.name
  virtual_network_id    = each.value.vnet_id
  registration_enabled  = each.value.registration
  tags                  = var.tags
}

# Static records managed by the reconciler land here too — Terraform owns
# only the seed records; drift detection is the reconciler's job.
resource "azurerm_private_dns_a_record" "static" {
  for_each            = var.a_records
  name                = each.key
  zone_name           = azurerm_private_dns_zone.zone.name
  resource_group_name = var.resource_group_name
  ttl                 = 300
  records             = [each.value]
}
