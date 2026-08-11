# tflint configuration for every root and module under terraform/.
#
# IMPORTANT — this file does NOT apply on its own. `tflint --recursive`
# re-executes the linter inside each directory and every one of those child
# runs looks for its own .tflint.hcl, so a config sitting here never reaches
# terraform/envs/lab or terraform/modules/*. Measured: with this file present
# but TFLINT_CONFIG_FILE unset, `tflint --only=<any azurerm rule>` fails with
# "Rule not found" in every subdirectory — i.e. the azurerm ruleset silently
# does not run and the lint passes vacuously.
#
# Set TFLINT_CONFIG_FILE to this file's absolute path before linting. CI does
# it in plan.yml's TFLint step; locally, AGENTS.md documents the same command.

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
