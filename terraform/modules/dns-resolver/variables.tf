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

variable "hub_address_space" {
  description = "Hub VNet CIDR. WR-06: both resolver subnets are carved from this range, so containment is provable here — where the subnets are created — instead of failing at Azure apply inside a cost-gated resolver session."
  type        = string
}

variable "hub_reserved_subnet_cidrs" {
  description = "Hub subnets that already exist in the VNet (VPN, shared). WR-06: the resolver subnets must not collide with them. No default on purpose: an omitted list would make the collision validations vacuously pass, so callers must state the reserved set explicitly (pass [] only for a genuinely empty VNet)."
  type        = list(string)
}

variable "inbound_subnet_cidr" {
  type    = string
  default = "10.10.2.0/28"

  validation {
    condition = try(
      tonumber(split("/", var.inbound_subnet_cidr)[1]) >= tonumber(split("/", var.hub_address_space)[1]) &&
      cidrsubnet(format("%s/%s", split("/", var.inbound_subnet_cidr)[0], split("/", var.hub_address_space)[1]), 0, 0)
      == cidrsubnet(var.hub_address_space, 0, 0),
    false)
    error_message = "inbound_subnet_cidr must be a valid IPv4 CIDR contained within hub_address_space — the inbound subnet is carved from the hub VNet, and Azure rejects out-of-range subnets only at apply time."
  }

  validation {
    condition = !try(
      cidrsubnet(format("%s/%d", split("/", var.inbound_subnet_cidr)[0], min(
        tonumber(split("/", var.inbound_subnet_cidr)[1]),
        tonumber(split("/", var.outbound_subnet_cidr)[1]),
      )), 0, 0)
      == cidrsubnet(format("%s/%d", split("/", var.outbound_subnet_cidr)[0], min(
        tonumber(split("/", var.inbound_subnet_cidr)[1]),
        tonumber(split("/", var.outbound_subnet_cidr)[1]),
      )), 0, 0),
    true)
    error_message = "inbound_subnet_cidr must not overlap outbound_subnet_cidr — each resolver endpoint needs its own delegated subnet, and an overlap plans cleanly and fails at Azure apply."
  }

  validation {
    condition = alltrue([
      for reserved in var.hub_reserved_subnet_cidrs :
      !try(
        cidrsubnet(format("%s/%d", split("/", var.inbound_subnet_cidr)[0], min(
          tonumber(split("/", var.inbound_subnet_cidr)[1]),
          tonumber(split("/", reserved)[1]),
        )), 0, 0)
        == cidrsubnet(format("%s/%d", split("/", reserved)[0], min(
          tonumber(split("/", var.inbound_subnet_cidr)[1]),
          tonumber(split("/", reserved)[1]),
        )), 0, 0),
      true)
    ])
    error_message = "inbound_subnet_cidr must not overlap any hub_reserved_subnet_cidrs entry (the hub's VPN and shared subnets) — the collision plans cleanly and fails at Azure apply."
  }
}

variable "outbound_subnet_cidr" {
  type    = string
  default = "10.10.2.16/28"

  validation {
    condition = try(
      tonumber(split("/", var.outbound_subnet_cidr)[1]) >= tonumber(split("/", var.hub_address_space)[1]) &&
      cidrsubnet(format("%s/%s", split("/", var.outbound_subnet_cidr)[0], split("/", var.hub_address_space)[1]), 0, 0)
      == cidrsubnet(var.hub_address_space, 0, 0),
    false)
    error_message = "outbound_subnet_cidr must be a valid IPv4 CIDR contained within hub_address_space — the outbound subnet is carved from the hub VNet, and Azure rejects out-of-range subnets only at apply time."
  }

  validation {
    condition = alltrue([
      for reserved in var.hub_reserved_subnet_cidrs :
      !try(
        cidrsubnet(format("%s/%d", split("/", var.outbound_subnet_cidr)[0], min(
          tonumber(split("/", var.outbound_subnet_cidr)[1]),
          tonumber(split("/", reserved)[1]),
        )), 0, 0)
        == cidrsubnet(format("%s/%d", split("/", reserved)[0], min(
          tonumber(split("/", var.outbound_subnet_cidr)[1]),
          tonumber(split("/", reserved)[1]),
        )), 0, 0),
      true)
    ])
    error_message = "outbound_subnet_cidr must not overlap any hub_reserved_subnet_cidrs entry (the hub's VPN and shared subnets) — the collision plans cleanly and fails at Azure apply."
  }
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
