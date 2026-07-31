variable "location" {
  type    = string
  default = "eastus"
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
