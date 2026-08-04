# Private DNS zone linked to hub + spokes.
# Auto-registration ON for spokes (VMs self-register), OFF for hub.

terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

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

# Terraform owns only these seed records. The reconciler later owns a disjoint
# managed record set so the two systems do not contend for the same names.
resource "azurerm_private_dns_a_record" "static" {
  for_each            = var.a_records
  name                = each.key
  zone_name           = azurerm_private_dns_zone.zone.name
  resource_group_name = var.resource_group_name
  ttl                 = 300
  records             = [each.value]
}
