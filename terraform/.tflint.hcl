# tflint configuration for every root and module under terraform/.
#
# `tflint --recursive` (what plan.yml's credential-free job runs) reads this
# file from the directory it is invoked in and passes it down, so the azurerm
# ruleset below applies to the bootstrap, lab, and cloudflare roots as well as
# to modules/*. Without a config file tflint loads only its built-in rules —
# the provider-specific checks that catch invalid VM sizes, deprecated
# arguments, and missing required attributes never run.

config {
  # Modules are linted through --recursive on their own directories; do not
  # descend into .terraform/modules copies of the same source.
  call_module_type = "local"
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "azurerm" {
  enabled = true
  source  = "github.com/terraform-linters/tflint-ruleset-azurerm"
  version = "0.32.0"
}
