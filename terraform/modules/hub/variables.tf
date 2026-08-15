variable "location" {
  description = "Azure region. No default on purpose: callers must pass the lab region explicitly, otherwise an omitted argument silently splits the deployment across regions (peering still works, so it fails as quota/latency/cost, not loudly)."
  type        = string
}

variable "vm_size" {
  description = "Azure VM SKU for the hub BIND9/WireGuard appliance. Must support the controller chosen in disk_controller_type."
  type        = string
  default     = "Standard_D2als_v7"
}

variable "disk_controller_type" {
  description = "Disk controller for the hub VM. Must match what vm_size supports: the v7 AMD families this lab can obtain (D*a*_v7, F*a*_v7) are NVMe-only, while B-series sizes are SCSI-only. A mismatch would plan cleanly and fail at Azure apply, and cross-controller changes require VM redeployment, so the known families are cross-checked below."
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

variable "resource_group_name" { type = string }

# The WR-06 CIDR checks below repeat one arithmetic idiom: two CIDRs overlap
# iff, at the coarser of the two prefix lengths, both collapse to the same
# network. The repetition across hub, dns-resolver, and the lab root is
# language-forced and accepted deliberately (2026-08-15 standards review):
# `validation` blocks cannot reference locals or other modules, and moving
# the checks off the variable boundary would strip fail-closed input
# validation from standalone module use. The canonical, fully commented form
# lives in envs/lab/main.tf (locals.routed_network_overlaps) — change the
# rule there first, then mirror it here.
variable "address_space" {
  description = "Hub VNet CIDR. NEW-WR-02: feeds local.internal_cidrs, so it renders into the public-IP hub's BIND ACLs, NSG allow rules, and NAT sources — validated like onprem_address_space."
  type        = string
  default     = "10.10.0.0/22"

  # PR #11 review: octets must be canonical (no leading zeros). Terraform's
  # CIDR functions read 010.010.0.0/16 as decimal 10.10.0.0/16, but the
  # ORIGINAL string is what renders into BIND and iptables — where iptables
  # reads the octets as octal (8.8.0.0/16), silently changing what the
  # RFC1918 check below believed it approved. Same pattern on every
  # IP/CIDR variable in this module and the spoke module.
  validation {
    condition = (
      can(cidrhost(var.address_space, 0)) &&
      can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])/(3[0-2]|[12]?[0-9])$", var.address_space))
    )
    error_message = "address_space must be an IPv4 CIDR in canonical octets (no leading zeros) like 10.10.0.0/22 — it renders into named.conf ACLs, NSG rules, and the NAT script, where non-canonical octets are re-interpreted (iptables reads them as octal)."
  }

  validation {
    condition = anytrue([
      for block in ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"] :
      tonumber(split("/", var.address_space)[1]) >= tonumber(split("/", block)[1]) &&
      try(cidrsubnet(format("%s/%s", split("/", var.address_space)[0], split("/", block)[1]), 0, 0) == block, false)
    ]) && tonumber(split("/", var.address_space)[1]) <= 29
    error_message = "address_space must be an RFC1918 subnet no smaller than /29 — it feeds the public-IP hub's BIND allow-query/allow-recursion, NSG allow rules, and NAT masquerade sources, so a public or over-broad range would expose an open recursive resolver."
  }
}

variable "vpn_subnet_cidr" {
  type    = string
  default = "10.10.0.0/27"

  # WR-06: carved from the hub VNet, so it must lie inside address_space —
  # a subnet outside the VNet range plans cleanly and fails at Azure apply.
  validation {
    condition = try(
      tonumber(split("/", var.vpn_subnet_cidr)[1]) >= tonumber(split("/", var.address_space)[1]) &&
      cidrsubnet(format("%s/%s", split("/", var.vpn_subnet_cidr)[0], split("/", var.address_space)[1]), 0, 0)
      == cidrsubnet(var.address_space, 0, 0),
    false)
    error_message = "vpn_subnet_cidr must be a valid IPv4 CIDR contained within address_space — it is carved from the hub VNet, and Azure rejects out-of-range subnets only at apply time."
  }
}

variable "shared_subnet_cidr" {
  type    = string
  default = "10.10.1.0/24"

  validation {
    condition = try(
      tonumber(split("/", var.shared_subnet_cidr)[1]) >= tonumber(split("/", var.address_space)[1]) &&
      cidrsubnet(format("%s/%s", split("/", var.shared_subnet_cidr)[0], split("/", var.address_space)[1]), 0, 0)
      == cidrsubnet(var.address_space, 0, 0),
    false)
    error_message = "shared_subnet_cidr must be a valid IPv4 CIDR contained within address_space — it is carved from the hub VNet, and Azure rejects out-of-range subnets only at apply time."
  }

  validation {
    condition = !try(
      cidrsubnet(format("%s/%d", split("/", var.shared_subnet_cidr)[0], min(
        tonumber(split("/", var.shared_subnet_cidr)[1]),
        tonumber(split("/", var.vpn_subnet_cidr)[1]),
      )), 0, 0)
      == cidrsubnet(format("%s/%d", split("/", var.vpn_subnet_cidr)[0], min(
        tonumber(split("/", var.shared_subnet_cidr)[1]),
        tonumber(split("/", var.vpn_subnet_cidr)[1]),
      )), 0, 0),
    true)
    error_message = "shared_subnet_cidr must not overlap vpn_subnet_cidr — overlapping subnet definitions plan cleanly and fail at Azure apply."
  }
}

variable "hub_vm_ip" {
  description = "Static private IP of the hub VM — referenced by spoke UDRs and VNet DNS"
  type        = string
  default     = "10.10.0.10"

  validation {
    condition = (
      can(cidrhost("${var.hub_vm_ip}/32", 0)) &&
      can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$", var.hub_vm_ip))
    )
    error_message = "hub_vm_ip must be a single IPv4 address without a mask, e.g. 10.10.0.10."
  }
}

variable "home_ip" {
  description = "Your home public IP as /32. NEVER widen. Not committed — set in tfvars (gitignored) or TF_VAR env. Sensitive so plan output redacts the NSG rules that carry it."
  type        = string
  sensitive   = true

  validation {
    condition = (
      can(cidrhost(var.home_ip, 0)) &&
      can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])/32$", var.home_ip))
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
  description = "On-prem CIDR. No default on purpose: callers must wire the same value the spokes receive, or hub NSG rules and the cloud-init render silently diverge from the spoke view."
  type        = string

  validation {
    condition = (
      can(cidrhost(var.onprem_address_space, 0)) &&
      can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])/(3[0-2]|[12]?[0-9])$", var.onprem_address_space))
    )
    error_message = "onprem_address_space must be an IPv4 CIDR like 10.20.0.0/16 — it renders into named.conf ACLs, WireGuard AllowedIPs, and NSG rules."
  }

  validation {
    condition = anytrue([
      for block in ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"] :
      tonumber(split("/", var.onprem_address_space)[1]) >= tonumber(split("/", block)[1]) &&
      try(cidrsubnet(format("%s/%s", split("/", var.onprem_address_space)[0], split("/", block)[1]), 0, 0) == block, false)
    ]) && tonumber(split("/", var.onprem_address_space)[1]) <= 30
    error_message = "onprem_address_space must be an RFC1918 subnet no smaller than /30 — this module renders it into the public-IP hub's NSG allow rules and BIND allow-query/allow-recursion, so a public or over-broad range (e.g. 0.0.0.0/0) would expose an open recursive resolver regardless of what the calling root validates."
  }
}

variable "spoke_address_spaces" {
  description = "Spoke CIDRs permitted to transit the hub NVA toward Internet and on-premises destinations. NEW-WR-02: each entry also feeds local.internal_cidrs and therefore the BIND ACLs, NSG allows, and NAT sources."
  type        = list(string)

  validation {
    condition = alltrue([
      for cidr in var.spoke_address_spaces :
      can(cidrhost(cidr, 0)) &&
      can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])/(3[0-2]|[12]?[0-9])$", cidr))
    ])
    error_message = "every spoke_address_spaces entry must be an IPv4 CIDR in canonical octets (no leading zeros) like 10.10.4.0/24 — each renders into named.conf ACLs, NSG rules, and the NAT script, where iptables reads non-canonical octets as octal."
  }

  validation {
    condition = alltrue([
      for cidr in var.spoke_address_spaces :
      anytrue([
        for block in ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"] :
        tonumber(split("/", cidr)[1]) >= tonumber(split("/", block)[1]) &&
        try(cidrsubnet(format("%s/%s", split("/", cidr)[0], split("/", block)[1]), 0, 0) == block, false)
      ]) && tonumber(split("/", cidr)[1]) <= 30
    ])
    error_message = "every spoke_address_spaces entry must be an RFC1918 subnet no smaller than /30 — each feeds the public-IP hub's BIND ACLs, NSG allow rules, and NAT sources, so a public or over-broad entry (e.g. 0.0.0.0/0) would silently expose an open recursive resolver."
  }
}

variable "wg_transfer_cidr" {
  description = "WireGuard transfer network allowed to query DNS and reach spoke workloads."
  type        = string
  default     = "172.16.0.0/24"

  validation {
    condition = (
      can(cidrhost(var.wg_transfer_cidr, 0)) &&
      can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])/(3[0-2]|[12]?[0-9])$", var.wg_transfer_cidr))
    )
    error_message = "wg_transfer_cidr must be an IPv4 CIDR like 172.16.0.0/24 — cidrhost() derives the WireGuard interface address from it and it renders into named.conf ACLs and NSG rules."
  }

  validation {
    condition = anytrue([
      for block in ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"] :
      tonumber(split("/", var.wg_transfer_cidr)[1]) >= tonumber(split("/", block)[1]) &&
      try(cidrsubnet(format("%s/%s", split("/", var.wg_transfer_cidr)[0], split("/", block)[1]), 0, 0) == block, false)
    ]) && tonumber(split("/", var.wg_transfer_cidr)[1]) >= 16 && tonumber(split("/", var.wg_transfer_cidr)[1]) <= 30 && can(cidrhost(var.wg_transfer_cidr, 2))
    error_message = "wg_transfer_cidr must be an RFC1918 subnet between /16 and /30 with at least two usable hosts — it feeds this module's public-facing DNS ACLs and NSG allow rules, and the derived WireGuard endpoint (.1) and peer (.2) must both exist inside it."
  }
}

variable "enable_private_resolver" {
  description = "Whether the cost-gated DNS Private Resolver is enabled. Controls only the matching tunnel-to-inbound-endpoint NSG rule in this module."
  type        = bool
  default     = false
}

variable "resolver_inbound_subnet_cidr" {
  description = "Dedicated DNS Private Resolver inbound subnet permitted as a tunnel-originated DNS destination only when enable_private_resolver is true."
  type        = string

  validation {
    condition = (
      can(cidrhost(var.resolver_inbound_subnet_cidr, 0)) &&
      can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])/(3[0-2]|[12]?[0-9])$", var.resolver_inbound_subnet_cidr))
    )
    error_message = "resolver_inbound_subnet_cidr must be a valid IPv4 CIDR such as 10.10.2.0/28."
  }

  # WR-06: carved from the hub VNet like vpn/shared, and additionally the NSG
  # rule this module builds for it assumes it is a distinct destination.
  validation {
    condition = try(
      tonumber(split("/", var.resolver_inbound_subnet_cidr)[1]) >= tonumber(split("/", var.address_space)[1]) &&
      cidrsubnet(format("%s/%s", split("/", var.resolver_inbound_subnet_cidr)[0], split("/", var.address_space)[1]), 0, 0)
      == cidrsubnet(var.address_space, 0, 0),
    false)
    error_message = "resolver_inbound_subnet_cidr must be contained within address_space — the resolver inbound subnet is carved from the hub VNet, and Azure rejects out-of-range subnets only at apply time."
  }

  validation {
    condition = !try(
      cidrsubnet(format("%s/%d", split("/", var.resolver_inbound_subnet_cidr)[0], min(
        tonumber(split("/", var.resolver_inbound_subnet_cidr)[1]),
        tonumber(split("/", var.vpn_subnet_cidr)[1]),
      )), 0, 0)
      == cidrsubnet(format("%s/%d", split("/", var.vpn_subnet_cidr)[0], min(
        tonumber(split("/", var.resolver_inbound_subnet_cidr)[1]),
        tonumber(split("/", var.vpn_subnet_cidr)[1]),
      )), 0, 0),
      true) && !try(
      cidrsubnet(format("%s/%d", split("/", var.resolver_inbound_subnet_cidr)[0], min(
        tonumber(split("/", var.resolver_inbound_subnet_cidr)[1]),
        tonumber(split("/", var.shared_subnet_cidr)[1]),
      )), 0, 0)
      == cidrsubnet(format("%s/%d", split("/", var.shared_subnet_cidr)[0], min(
        tonumber(split("/", var.resolver_inbound_subnet_cidr)[1]),
        tonumber(split("/", var.shared_subnet_cidr)[1]),
      )), 0, 0),
    true)
    error_message = "resolver_inbound_subnet_cidr must not overlap the VPN or shared subnets — overlapping subnet definitions plan cleanly and fail at Azure apply."
  }
}

variable "lab_zone" {
  description = "On-prem forward zone, e.g. lab.dwsolution.co"
  type        = string
}

variable "onprem_dns_ip" {
  description = "Laptop BIND9 IP reachable via tunnel"
  type        = string

  validation {
    condition = (
      can(cidrhost("${var.onprem_dns_ip}/32", 0)) &&
      can(regex("^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])$", var.onprem_dns_ip))
    )
    error_message = "onprem_dns_ip must be a single IPv4 address without a mask — it renders into the named.conf forwarders clause and WireGuard AllowedIPs."
  }
}

variable "wg_peer_public_key" {
  description = "Laptop WireGuard public key (public keys are safe to commit). WR-07: shape-validated here as well as in the calling root — this module renders the value straight into cloud-init."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9+/]{43}=$", var.wg_peer_public_key))
    error_message = "wg_peer_public_key must be a base64-encoded 32-byte WireGuard public key — exactly 43 base64 characters followed by '=' (e.g. the output of `wg pubkey`). An empty or malformed value would plan cleanly, bill the hub VM, and fail WireGuard setup on first boot."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
