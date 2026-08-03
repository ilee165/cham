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

variable "hub_nva_ip" {
  description = "Hub NVA private IP used as the next hop for resolver replies to WireGuard and on-premises clients."
  type        = string
}

variable "onprem_address_space" {
  description = "On-premises source prefix whose resolver replies must return through the hub NVA."
  type        = string
}

variable "wg_transfer_cidr" {
  description = "WireGuard transfer prefix whose resolver replies must return through the hub NVA."
  type        = string
}

variable "forwarding_vnet_links" {
  description = "Virtual networks whose Azure DNS queries should be subject to this resolver's forwarding rules."
  type        = map(string)
}

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

variable "tags" {
  type    = map(string)
  default = {}
}
