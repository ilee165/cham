variable "subscription_id" {
  description = "Azure subscription ID that will contain the Terraform state resources."
  type        = string
}

variable "principal_object_id" {
  description = "Microsoft Entra object ID granted access to the Terraform state container."
  type        = string
}
