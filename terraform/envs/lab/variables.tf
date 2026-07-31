variable "location" {
  type    = string
  default = "eastus"
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

variable "wg_peer_public_key" { type = string }

variable "enable_private_resolver" {
  description = "~$360/mo when true. Single-session use only."
  type        = bool
  default     = false
}

variable "alert_email" { type = string }

variable "budget_start_date" {
  description = "RFC3339 first-of-month, e.g. 2026-08-01T00:00:00Z"
  type        = string
}
