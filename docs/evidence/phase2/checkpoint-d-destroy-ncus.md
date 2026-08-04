# Phase 2 Checkpoint D — North Central US Lab Stack Destroy

Executed 2026-08-03 as gate 1 of the eastus2 recovery selected after the
Checkpoint C capacity failure (see `checkpoint-c-four-core-plan.md`, "Region
capacity probe and selected recovery").

## Approval boundary

- Saved plan: `checkpoint-d-destroy-ncus-35.tfplan`, generated from commit
  `e0c1c9c` with the state-matching North Central US configuration.
- SHA-256:
  `7CE771B96D65E5B7DD53CD213AB616FC12EA4567782303BED5009BC5D654395C`.
- Plan delta: 0 add, 0 change, 35 destroy; zero warnings. The resource list
  was reviewed before approval: the full `rg-cham-lab` stack only — hub
  (VM, NIC, public IP, VNet, subnets, NSG, associations), both spokes
  (VNets, subnets, NSGs, route tables, associations, peerings, app test VM,
  both test NICs), private DNS zone with links and the seed record, and the
  subscription budget. No bootstrap resource appeared in the plan.
- The operator approved this exact hash at 2026-08-03 18:05 EDT and directed
  the sequence to continue through Checkpoint B plan generation, with review
  at the next checkpoint. The artifact hash was re-verified immediately
  before apply and matched.

## Apply outcome

- `terraform apply` of the saved plan started at about 22:05 UTC and
  completed at about 22:10 UTC with exit code 0.
- Result: `Apply complete! Resources: 0 added, 0 changed, 35 destroyed.`
- Post-apply verification: `terraform state list` returns an empty lab
  state; `az group exists` reports `rg-cham-lab` false and `rg-cham-tfstate`
  true (6-resource bootstrap stack retained).
- The consumed plan artifact is retained under its original name for the
  audit trail; it can never apply again because the state serial has moved.
- The subscription budget resource was destroyed with the stack, as recorded
  in the approval note. Checkpoint B recreates it; the gap carries no compute
  spend because no lab resources remain.

## Cost effect

All lab compute, disk, public IP, DNS, and networking resources in North
Central US are deleted. Remaining Azure spend is limited to the retained
bootstrap stack (state storage account) and any already-accrued charges.
