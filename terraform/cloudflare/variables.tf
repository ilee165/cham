variable "zone_name" {
  type    = string
  default = "dwsolution.co"
}

variable "www_public_ip" {
  description = "Public target for www (e.g. Cloudflare Pages / placeholder)"
  type        = string
}
