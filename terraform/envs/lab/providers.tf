terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  backend "azurerm" {
    # Values from bootstrap output. Blob lease provides state locking natively.
    resource_group_name  = "rg-aletheia-tfstate"
    storage_account_name = "REPLACE_FROM_BOOTSTRAP_OUTPUT"
    container_name       = "tfstate"
    key                  = "lab.tfstate"
  }
}

provider "azurerm" {
  features {}
  # Local: az login. CI: OIDC federation — no client secrets anywhere.
}
