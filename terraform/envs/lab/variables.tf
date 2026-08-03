variable "location" {
  type    = string
  default = "northcentralus"
}

variable "vm_size" {
  description = "VM SKU for the hub appliance."
  type        = string
  default     = "Standard_B2ats_v2"
}

variable "test_vm_size" {
  description = "VM SKU for temporary private verification VMs."
  type        = string
  default     = "Standard_D2als_v6"
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
}

variable "onprem_dns_ip" {
  description = "Laptop BIND9 tunnel IP"
  type        = string
  default     = "172.16.0.2"
}

variable "wg_transfer_cidr" {
  description = "WireGuard transfer network allowed to reach hub DNS and spoke workloads."
  type        = string
  default     = "172.16.0.0/24"
}

variable "wg_peer_public_key" { type = string }

variable "enable_private_resolver" {
  description = "Cost-bearing Azure DNS Private Resolver feature. Keep false during Phase 2."
  type        = bool
  default     = false
}

variable "enable_test_vm" {
  description = "Create temporary private verification VMs in both spokes."
  type        = bool
  default     = false
}

variable "alert_email" { type = string }

variable "budget_start_date" {
  description = "RFC3339 first-of-month, e.g. 2026-08-01T00:00:00Z"
  type        = string
}
