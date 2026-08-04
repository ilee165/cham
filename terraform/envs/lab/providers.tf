terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  backend "azurerm" {
    # storage_account_name, subscription_id, and tenant_id come from a local
    # gitignored *.tfbackend file. Blob leases provide state locking natively.
    resource_group_name = "rg-cham-tfstate"
    container_name      = "tfstate"
    key                 = "lab.tfstate"
    use_azuread_auth    = true
  }
}

# resource_provider_registrations = "none" disables automatic RP registration,
# so a FRESH subscription must pre-register the namespaces this stack touches
# or the first apply fails midway with MissingSubscriptionRegistration errors.
# Required here:
#   Microsoft.Network     — VNets/subnets/NSGs/peering/UDRs, private DNS zones,
#                           DNS Private Resolver
#   Microsoft.Compute     — VMs, managed disks
#   Microsoft.Consumption — budget alert
#   Microsoft.Resources   — resource groups (normally registered by default)
# One-time setup per subscription:
#   for rp in Microsoft.Network Microsoft.Compute Microsoft.Consumption Microsoft.Resources; do
#     az provider register --namespace "$rp"; done
provider "azurerm" {
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
  features {}
  # Local: az login. CI: OIDC federation — no client secrets anywhere.
}
