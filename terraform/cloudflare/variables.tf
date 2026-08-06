variable "zone_name" {
  type    = string
  default = "dwsolution.co"
}

variable "www_public_target" {
  description = "Public www target hostname (GitHub Pages site)"
  type        = string
  default     = "ilee165.github.io"
}
