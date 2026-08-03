variable "location" {
  type    = string
  default = "eastus2"
}

variable "vm_size" {
  description = "VM SKU for the hub appliance. v7 AMD sizes are NVMe-boot-only; the VM resources set disk_controller_type accordingly."
  type        = string
  default     = "Standard_D2als_v7"
}

variable "test_vm_size" {
  description = "VM SKU for temporary private verification VMs. One vCPU keeps the paired topology within the lab's four-core regional quota."
  type        = string
  default     = "Standard_F1als_v7"
}

variable "subscription_id" { type = string }

variable "public_zone" {
  description = "Public apex zone on Cloudflare"
  type        = string
  default     = "dwsolution.co"
}

variable "lab_zone" {
  type    = string
  default = "lab.dwsolution.co"
}

variable "home_ip" {
  description = "Home public IP /32. Set via TF_VAR_home_ip or terraform.tfvars (gitignored). NOT committed."
  type        = string

  validation {
    condition = (
      can(cidrhost(var.home_ip, 0)) &&
      can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/32$", var.home_ip))
    )
    error_message = "home_ip must be one valid IPv4 host expressed as a /32."
  }
}

variable "ssh_public_key" { type = string }

variable "onprem_address_space" {
  type    = string
  default = "10.20.0.0/16"

  validation {
    condition = (
      can(cidrhost(var.onprem_address_space, 0)) &&
      can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/[0-9]{1,2}$", var.onprem_address_space))
    )
    error_message = "onprem_address_space must be an IPv4 CIDR like 10.20.0.0/16 — it renders into BIND ACLs, WireGuard AllowedIPs, NSG prefixes, and spoke UDRs, where a typo becomes a boot-time BIND failure instead of a plan error."
  }
}

variable "onprem_dns_ip" {
  description = "Laptop BIND9 tunnel IP"
  type        = string
  default     = "172.16.0.2"

  validation {
    condition = (
      can(cidrhost("${var.onprem_dns_ip}/32", 0)) &&
      can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}$", var.onprem_dns_ip))
    )
    error_message = "onprem_dns_ip must be a single IPv4 address without a mask, e.g. 172.16.0.2."
  }

  validation {
    condition = anytrue([
      for cidr in [var.wg_transfer_cidr, var.onprem_address_space] :
      try(cidrsubnet(format("%s/%s", var.onprem_dns_ip, split("/", cidr)[1]), 0, 0) == cidrsubnet(cidr, 0, 0), false)
    ])
    error_message = "onprem_dns_ip must lie inside wg_transfer_cidr or onprem_address_space — the hub only routes those prefixes into the WireGuard tunnel (AllowedIPs), so a DNS target outside both can never be reached."
  }
}

variable "wg_transfer_cidr" {
  description = "WireGuard transfer network allowed to reach hub DNS and spoke workloads."
  type        = string
  default     = "172.16.0.0/24"

  validation {
    condition = (
      can(cidrhost(var.wg_transfer_cidr, 0)) &&
      can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/[0-9]{1,2}$", var.wg_transfer_cidr))
    )
    error_message = "wg_transfer_cidr must be an IPv4 CIDR like 172.16.0.0/24 — the WireGuard interface address is derived from it and it renders into BIND ACLs and NSG prefixes."
  }
}

variable "wg_peer_public_key" { type = string }

variable "enable_private_resolver" {
  description = "Cost-bearing Azure DNS Private Resolver feature. Keep false during Phase 2."
  type        = bool
  default     = false
}

variable "enable_test_vm" {
  description = "Deprecated compatibility flag that creates both temporary test VMs. Prefer the per-spoke overrides so partial or quota-limited state can be represented safely."
  type        = bool
  default     = false

  validation {
    condition = !var.enable_test_vm || alltrue([
      var.enable_test_vm_app != null,
      var.enable_test_vm_mgmt != null,
      var.enable_test_nic_app != null,
      var.enable_test_nic_mgmt != null,
    ])
    error_message = "The deprecated enable_test_vm=true setting is ambiguous. Set all four per-spoke VM/NIC overrides explicitly before planning."
  }
}

variable "enable_test_vm_app" {
  description = "Optional app-spoke override. Null inherits deprecated enable_test_vm; set explicitly for any state-backed plan."
  type        = bool
  default     = null
}

variable "enable_test_vm_mgmt" {
  description = "Optional management-spoke override. Null inherits deprecated enable_test_vm; set explicitly for any state-backed plan."
  type        = bool
  default     = null
}

variable "enable_test_nic_app" {
  description = "Optional app test-NIC override. Null follows the resolved app VM flag. Set explicitly for a partial-state plan."
  type        = bool
  default     = null
}

variable "enable_test_nic_mgmt" {
  description = "Optional management test-NIC override. Null follows the resolved management VM flag. Set true with enable_test_vm_mgmt=false to preserve a quota-blocked NIC."
  type        = bool
  default     = null
}

variable "alert_email" { type = string }

variable "budget_amount" {
  description = "Monthly budget alert threshold in USD. Default 50 = one quarter of the $200 trial credit, so the 50%/90% notifications fire long before the credit is at risk. Notification-only — Azure has no automatic spend cap; the real kill switch is .github/workflows/destroy.yml."
  type        = number
  default     = 50
}

variable "budget_start_date" {
  description = "RFC3339 first-of-month, e.g. 2026-08-01T00:00:00Z"
  type        = string

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-01T00:00:00(Z|[+]00:00)$", var.budget_start_date))
    error_message = "budget_start_date must be UTC midnight on the FIRST of a month, e.g. 2026-08-01T00:00:00Z — Azure rejects any other start_date at apply time with an opaque error, so catch it at plan time."
  }
}
