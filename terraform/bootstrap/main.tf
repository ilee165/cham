# Bootstrap: storage account + container for Terraform remote state.
# Chicken-and-egg: this stack uses LOCAL state. Apply once, keep the local
# tfstate somewhere safe because it contains the state-storage resource IDs.

terraform {
  required_version = ">= 1.9"

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
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
  storage_use_azuread             = true
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
  #checkov:skip=CKV_AZURE_206:owner=repository-maintainer; exact=azurerm_storage_account.state; rationale=LRS is the approved cost-controlled lab-state tier; control=blob versioning, seven-day soft delete, and secured bootstrap state provide recovery.
  #checkov:skip=CKV_AZURE_59:owner=repository-maintainer; exact=azurerm_storage_account.state; rationale=the operator and CI require the public service endpoint; control=anonymous access is disabled, TLS 1.2 and Entra RBAC are required, and shared keys are disabled.
  #checkov:skip=CKV_AZURE_33:owner=repository-maintainer; exact=azurerm_storage_account.state; rationale=Checkov does not correlate the current standalone queue-properties resource; control=azurerm_storage_account_queue_properties.state logs queue reads, writes, and deletes with seven-day retention.
  #checkov:skip=CKV2_AZURE_1:owner=repository-maintainer; exact=azurerm_storage_account.state; rationale=a customer-managed-key stack is disproportionate for this disposable lab; control=Microsoft-managed encryption, Entra RBAC, versioning, and soft delete remain enabled.
  #checkov:skip=CKV2_AZURE_33:owner=repository-maintainer; exact=azurerm_storage_account.state; rationale=a private endpoint would make the bootstrap backend unreachable from the approved home and hosted-CI workflows; control=Entra RBAC, no shared keys, no anonymous access, and TLS 1.2 protect the public endpoint.
  name                            = "stchamtf${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.state.name
  location                        = azurerm_resource_group.state.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = 7
    }

    container_delete_retention_policy {
      days = 7
    }
  }

}

resource "azurerm_storage_account_queue_properties" "state" {
  storage_account_id = azurerm_storage_account.state.id

  logging {
    delete                = true
    read                  = true
    write                 = true
    version               = "1.0"
    retention_policy_days = 7
  }
}

resource "azurerm_storage_container" "state" {
  #checkov:skip=CKV2_AZURE_21:owner=repository-maintainer; exact=azurerm_storage_container.state; rationale=the minimal bootstrap stack has no Log Analytics destination for blob read logs; control=Entra RBAC, no shared keys, versioning, soft delete, and Azure control-plane activity logs protect and audit the lab backend.
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
}

resource "azurerm_role_assignment" "state_blob_data_contributor" {
  scope                = azurerm_storage_account.state.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.principal_object_id
}

output "backend_config" {
  value = <<-EOT
    Create a gitignored backend.auto.tfbackend file for each remote-state root:
      storage_account_name = "${azurerm_storage_account.state.name}"
      subscription_id      = "${var.subscription_id}"
      tenant_id            = "<approved-tenant-id>"
  EOT
}
