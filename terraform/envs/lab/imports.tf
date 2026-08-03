# TEMPORARY — Checkpoint B recovery imports (2026-08-03).
#
# eastus2 Network RP read-consistency lag after the same-name resource group
# was recreated across regions: several resources were created successfully
# (activity log: Succeeded) but post-create reads returned 404, so the
# provider reported "inconsistent result" and dropped them from state. The
# hub public IP and app VNet import blocks from round two have landed and
# were removed. This round imports the app-to-hub peering, which Azure shows
# as Connected. Delete this file after the remainder apply lands it.

import {
  to = module.spoke_app.azurerm_virtual_network_peering.spoke_to_hub
  id = "/subscriptions/${var.subscription_id}/resourceGroups/rg-cham-lab/providers/Microsoft.Network/virtualNetworks/vnet-app/virtualNetworkPeerings/peer-app-to-hub"
}
