# Bootstrap: storage account + container for Terraform remote state.
# Chicken-and-egg: this stack uses LOCAL state. Apply once, keep the local
# tfstate somewhere safe (it only contains these three resources).

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_resource_group" "state" {
  name     = "rg-cham-tfstate"
  location = "eastus"
}

resource "azurerm_storage_account" "state" {
  name                            = "stchamtf${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.state.name
  location                        = azurerm_resource_group.state.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
}

resource "azurerm_storage_container" "state" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
}

output "backend_config" {
  value = <<-EOT
    Add to envs/lab/providers.tf backend block:
      resource_group_name  = "${azurerm_resource_group.state.name}"
      storage_account_name = "${azurerm_storage_account.state.name}"
      container_name       = "tfstate"
      key                  = "lab.tfstate"
  EOT
}
