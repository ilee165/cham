variable "zone_name" { type = string }
variable "resource_group_name" { type = string }

variable "vnet_links" {
  type = map(object({
    vnet_id      = string
    registration = bool
  }))
}

variable "a_records" {
  description = "Seed A records: name => IP"
  type        = map(string)
  default     = {}
}

variable "tags" {
  type    = map(string)
  default = {}
}
