# TEMPORARY — Checkpoint B recovery imports (2026-08-03).
#
# The first eastus2 Checkpoint B apply hit a Network RP read-consistency lag:
# these two resources were created successfully (activity log: Succeeded) but
# the provider's post-create read returned 404, so they were dropped from
# state as "provider produced inconsistent result". CLI `terraform import`
# trips a legacy import-graph for_each limitation in this configuration, so
# the imports ride the plan instead. Delete this file after the remainder
# apply lands both imports.

import {
  to = module.hub.azurerm_public_ip.hub
  id = "/subscriptions/${var.subscription_id}/resourceGroups/rg-cham-lab/providers/Microsoft.Network/publicIPAddresses/pip-hub-ddi"
}

import {
  to = module.spoke_app.azurerm_virtual_network.spoke
  id = "/subscriptions/${var.subscription_id}/resourceGroups/rg-cham-lab/providers/Microsoft.Network/virtualNetworks/vnet-app"
}
