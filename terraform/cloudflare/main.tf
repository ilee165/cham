# Public DNS for dwsolution.co — the external half of the split horizon.
# Separate state from the Azure stack: different provider, different blast
# radius, different credential (scoped API token, Zone:DNS:Edit only).

terraform {
  required_version = ">= 1.9"
  required_providers {
    # Floor matches the real requirement: cloudflare_record.content only
    # exists in late 4.x — "~> 4.0" would admit releases where init against
    # a rebuilt lockfile succeeds but the config cannot plan.
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.52"
    }
  }
  backend "azurerm" {
    # storage_account_name, subscription_id, and tenant_id come from a local
    # gitignored *.tfbackend file. Credentials remain environment-sourced.
    resource_group_name = "rg-cham-tfstate"
    container_name      = "tfstate"
    key                 = "cloudflare.tfstate"
    use_azuread_auth    = true
  }
}

provider "cloudflare" {
  # CLOUDFLARE_API_TOKEN env var. Scoped token, NOT a global API key.
}

data "cloudflare_zone" "apex" {
  name = var.zone_name
}

# The public answer for www — the split-horizon counterpart lives in the
# internal BIND9 override zone and returns the hub's private IP for the
# same name.
resource "cloudflare_record" "www" {
  zone_id = data.cloudflare_zone.apex.id
  name    = "www"
  type    = "CNAME"
  content = var.www_public_target
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
