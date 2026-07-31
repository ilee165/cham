variable "enabled" {
  description = "Master switch. ~$360/mo when true. Default false, keep it that way."
  type        = bool
  default     = false
}

variable "location" {
  type    = string
  default = "eastus"
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
variable "onprem_dns_ip" { type = string }
