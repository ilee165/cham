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

provider "azurerm" {
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
  features {}
  # Local: az login. CI: OIDC federation — no client secrets anywhere.
}
