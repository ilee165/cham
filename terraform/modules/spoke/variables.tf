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
  description = "Disk controller for the verification VM. Must match what vm_size supports: the v7 AMD families this lab can obtain are NVMe-only, while B-series and most v5/v6 sizes are SCSI-only or SCSI-default. A mismatch plans cleanly and fails at Azure apply, and cross-controller changes require VM redeployment."
  type        = string
  default     = "NVMe"

  validation {
    condition     = contains(["SCSI", "NVMe"], var.disk_controller_type)
    error_message = "disk_controller_type must be \"SCSI\" or \"NVMe\"."
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

variable "onprem_address_space" {
  description = "On-prem CIDR reachable via the tunnel"
  type        = string
  default     = "10.20.0.0/16"
}

variable "wg_transfer_cidr" {
  description = "WireGuard transfer network allowed to reach spoke workloads."
  type        = string
  default     = "172.16.0.0/24"
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
