variable "name" {
  description = "Spoke name, e.g. app, mgmt"
  type        = string
}

variable "location" {
  type    = string
  default = "eastus"
}

variable "vm_size" {
  description = "Azure VM SKU for the temporary verification VM."
  type        = string
  default     = "Standard_D2als_v6"
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
