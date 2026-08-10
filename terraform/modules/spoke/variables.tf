variable "name" {
  description = "Spoke name, e.g. app, mgmt"
  type        = string
}

variable "location" {
  description = "Azure region. No default on purpose: callers must pass the lab region explicitly, otherwise an omitted argument silently splits the deployment across regions."
  type        = string
}

variable "vm_size" {
  description = "Azure VM SKU for the temporary verification VM. Must support the controller chosen in disk_controller_type."
  type        = string
  default     = "Standard_F1als_v7"
}

variable "disk_controller_type" {
  description = "Disk controller for the verification VM. Must match what vm_size supports: the v7 AMD families this lab can obtain are NVMe-only, while B-series sizes are SCSI-only. A mismatch would plan cleanly and fail at Azure apply, so the known families are cross-checked below."
  type        = string
  default     = "NVMe"

  validation {
    condition     = contains(["SCSI", "NVMe"], var.disk_controller_type)
    error_message = "disk_controller_type must be \"SCSI\" or \"NVMe\"."
  }

  validation {
    condition     = !(can(regex("^Standard_B", var.vm_size)) && var.disk_controller_type == "NVMe")
    error_message = "vm_size is a B-series (SCSI-only) size but disk_controller_type is \"NVMe\" — this pairing plans cleanly and fails at Azure apply. Set disk_controller_type = \"SCSI\" when falling back to a B-series SKU."
  }

  validation {
    condition     = !(can(regex("^Standard_[DF][0-9]+a[a-z]*_v7$", var.vm_size)) && var.disk_controller_type == "SCSI")
    error_message = "vm_size is an NVMe-only v7 AMD size but disk_controller_type is \"SCSI\". Set disk_controller_type = \"NVMe\" for D*a*_v7 / F*a*_v7 sizes. (Guard covers the families this lab uses; verify controller support for other exotic sizes.)"
  }
}

variable "resource_group_name" {
  type = string
}

variable "address_space" {
  description = "Spoke VNet CIDR, e.g. 10.10.4.0/22"
  type        = string
}

variable "subnets" {
  description = "Map of subnet name => CIDR"
  type        = map(string)
}

variable "dns_servers" {
  description = "Custom DNS servers for the VNet (hub BIND9 VM IP)"
  type        = list(string)
  default     = []
}

variable "hub_vnet_id" {
  type = string
}

variable "hub_vnet_name" {
  type = string
}

variable "hub_address_space" {
  type = string
}

variable "hub_nva_ip" {
  description = "Private IP of the hub BIND9/WireGuard VM (next hop)"
  type        = string
}

variable "spoke_address_spaces" {
  description = "All spoke CIDRs in the lab, including this spoke's own. DenyOtherSpokes blocks them ahead of Azure's default AllowVnetInBound (NEW-IN-04 — was a hardcoded 10.10.0.0/16 that missed spokes outside the default supernet); this spoke's own traffic is admitted earlier by AllowIntraSpoke."
  type        = list(string)

  validation {
    condition = alltrue([
      for cidr in var.spoke_address_spaces :
      can(cidrhost(cidr, 0)) &&
      can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])/(3[0-2]|[12]?[0-9])$", cidr))
    ])
    error_message = "every spoke_address_spaces entry must be an IPv4 CIDR in canonical octets (no leading zeros) like 10.10.4.0/24 — the list renders directly into this spoke's NSG deny rule."
  }

  # PR #11 review: alltrue([]) is true, and an NSG rule whose
  # source_address_prefixes is empty passes plan but fails at ARM apply.
  validation {
    condition     = length(var.spoke_address_spaces) > 0
    error_message = "spoke_address_spaces must not be empty — DenyOtherSpokes renders it as source_address_prefixes, and ARM rejects an NSG rule with no source."
  }

  validation {
    condition     = contains(var.spoke_address_spaces, var.address_space)
    error_message = "spoke_address_spaces must include this spoke's own address_space — the list is the complete set of lab spoke CIDRs (own-spoke traffic is admitted earlier by AllowIntraSpoke, so including it here is safe and required)."
  }
}

variable "onprem_address_space" {
  description = "On-prem CIDR reachable via the tunnel"
  type        = string
  default     = "10.20.0.0/16"

  # PR #11 review: canonical octets only — Terraform reads 010.x as decimal
  # while downstream consumers can re-interpret the original string as octal.
  validation {
    condition     = can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])/(3[0-2]|[12]?[0-9])$", var.onprem_address_space))
    error_message = "onprem_address_space must be an IPv4 CIDR in canonical octets (no leading zeros)."
  }

  validation {
    condition = anytrue([
      for block in ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"] :
      try(tonumber(split("/", var.onprem_address_space)[1]) >= tonumber(split("/", block)[1]) &&
      cidrsubnet(format("%s/%s", split("/", var.onprem_address_space)[0], split("/", block)[1]), 0, 0) == block, false)
    ]) && try(tonumber(split("/", var.onprem_address_space)[1]) <= 30, false)
    error_message = "onprem_address_space must be an RFC1918 subnet no smaller than /30 — it renders into this spoke's NSG prefixes and UDR routes, so a public or over-broad range would open the spoke's east-west allow rules."
  }
}

variable "wg_transfer_cidr" {
  description = "WireGuard transfer network allowed to reach spoke workloads."
  type        = string
  default     = "172.16.0.0/24"

  validation {
    condition     = can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])/(3[0-2]|[12]?[0-9])$", var.wg_transfer_cidr))
    error_message = "wg_transfer_cidr must be an IPv4 CIDR in canonical octets (no leading zeros)."
  }

  validation {
    condition = anytrue([
      for block in ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"] :
      try(tonumber(split("/", var.wg_transfer_cidr)[1]) >= tonumber(split("/", block)[1]) &&
      cidrsubnet(format("%s/%s", split("/", var.wg_transfer_cidr)[0], split("/", block)[1]), 0, 0) == block, false)
    ]) && try(tonumber(split("/", var.wg_transfer_cidr)[1]) >= 16 && tonumber(split("/", var.wg_transfer_cidr)[1]) <= 30, false)
    error_message = "wg_transfer_cidr must be an RFC1918 subnet between /16 and /30 — it renders into this spoke's NSG allow prefixes, so a public or over-broad range would open the spoke to non-tunnel sources."
  }
}

variable "enable_test_vm" {
  description = "Create one temporary private verification VM in this spoke."
  type        = bool
  default     = false

  validation {
    condition     = !var.enable_test_vm || var.enable_test_nic != false
    error_message = "enable_test_nic cannot be false while enable_test_vm is true."
  }
}

variable "enable_test_nic" {
  description = "Optional NIC lifecycle override for partially applied test workloads. Null follows enable_test_vm; true with enable_test_vm=false preserves a NIC whose VM was quota-blocked."
  type        = bool
  default     = null
}

variable "test_vm_subnet_key" {
  description = "Key in var.subnets whose subnet hosts the test VM NIC. Defaults to the sole subnet; must be set explicitly once the spoke has more than one subnet — the plan then fails loudly instead of silently re-homing the NIC to whichever key sorts first."
  type        = string
  default     = null
}

variable "admin_username" {
  description = "Administrator username for the temporary verification VM."
  type        = string
  default     = "labadmin"
}

variable "ssh_public_key" {
  description = "SSH public key for the temporary private verification VM."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
