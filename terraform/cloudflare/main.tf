# Public DNS for dwsolution.co — the external half of the split horizon.
# Separate state from the Azure stack: different provider, different blast
# radius, different credential (scoped API token, Zone:DNS:Edit only).

terraform {
  required_version = ">= 1.9"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
  backend "azurerm" {
    resource_group_name  = "rg-cham-tfstate"
    storage_account_name = "REPLACE_FROM_BOOTSTRAP_OUTPUT"
    container_name       = "tfstate"
    key                  = "cloudflare.tfstate"
  }
}

provider "cloudflare" {
  # CLOUDFLARE_API_TOKEN env var. Scoped token, NOT a global API key.
}

data "cloudflare_zone" "apex" {
  name = var.zone_name
}

# The public answer for www — the split-horizon counterpart lives in the
# internal BIND9 view and returns a private IP for the same name.
resource "cloudflare_record" "www" {
  zone_id = data.cloudflare_zone.apex.id
  name    = "www"
  type    = "A"
  content = var.www_public_ip
  ttl     = 300
  proxied = false # keep dig-able; proxying returns Cloudflare edge IPs
}

resource "cloudflare_record" "lab_marker" {
  zone_id = data.cloudflare_zone.apex.id
  name    = "external-check"
  type    = "TXT"
  content = "resolved-via=cloudflare-public"
  ttl     = 300
}
