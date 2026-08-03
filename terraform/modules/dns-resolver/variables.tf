variable "enabled" {
  description = "Master switch. ~$360/mo when true. Default false, keep it that way."
  type        = bool
  default     = false
}

variable "location" {
  description = "Azure region. No default on purpose: callers must pass the lab region explicitly, otherwise an omitted argument silently splits the deployment across regions."
  type        = string
}

variable "resource_group_name" { type = string }
variable "hub_vnet_id" { type = string }
variable "hub_vnet_name" { type = string }

variable "inbound_subnet_cidr" {
  type    = string
  default = "10.10.2.0/28"
}

variable "outbound_subnet_cidr" {
  type    = string
  default = "10.10.2.16/28"
}

variable "lab_zone" { type = string }

variable "hub_dns_ip" {
  description = "Hub BIND9 VM private IP — the in-VNet forwarding target that already relays the lab zone on-prem across the WireGuard tunnel. The laptop tunnel IP is NOT reachable from the resolver outbound subnet."
  type        = string
}
