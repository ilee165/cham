variable "location" {
  type    = string
  default = "eastus"
}

variable "vm_size" {
  description = "Azure VM SKU for the hub BIND9/WireGuard appliance."
  type        = string
  default     = "Standard_B2ats_v2"
}

variable "resource_group_name" { type = string }

variable "address_space" {
  type    = string
  default = "10.10.0.0/22"
}

variable "vpn_subnet_cidr" {
  type    = string
  default = "10.10.0.0/27"
}

variable "shared_subnet_cidr" {
  type    = string
  default = "10.10.1.0/24"
}

variable "hub_vm_ip" {
  description = "Static private IP of the hub VM — referenced by spoke UDRs and VNet DNS"
  type        = string
  default     = "10.10.0.10"
}

variable "home_ip" {
  description = "Your home public IP as /32. NEVER widen. Not committed — set in tfvars (gitignored) or TF_VAR env."
  type        = string

  validation {
    condition = (
      can(cidrhost(var.home_ip, 0)) &&
      can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/32$", var.home_ip))
    )
    error_message = "home_ip must be one valid IPv4 host expressed as a /32."
  }
}

variable "admin_username" {
  type    = string
  default = "labadmin"
}

variable "ssh_public_key" { type = string }

variable "onprem_address_space" {
  type    = string
  default = "10.20.0.0/16"
}

variable "spoke_address_spaces" {
  description = "Spoke CIDRs permitted to transit the hub NVA toward Internet and on-premises destinations."
  type        = list(string)
}

variable "wg_transfer_cidr" {
  description = "WireGuard transfer network allowed to query DNS and reach spoke workloads."
  type        = string
  default     = "172.16.0.0/24"
}

variable "lab_zone" {
  description = "On-prem forward zone, e.g. lab.dwsolution.co"
  type        = string
}

variable "onprem_dns_ip" {
  description = "Laptop BIND9 IP reachable via tunnel"
  type        = string
}

variable "wg_peer_public_key" {
  description = "Laptop WireGuard public key (public keys are safe to commit)"
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
