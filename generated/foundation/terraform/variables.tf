# AUTO-GENERATED — DO NOT EDIT. Source: knowledge/foundation/landing_zone.yaml. Regenerate with `altitude generate`.
variable "organization_name" {
  type        = string
  description = "Snowflake organization name"
}

variable "account_name" {
  type        = string
  description = "Snowflake account name"
}

variable "terraform_user" {
  type        = string
  description = "Service user Terraform authenticates as"
}

variable "terraform_role" {
  type        = string
  description = "Role Terraform uses (needs SYSADMIN + SECURITYADMIN rights)"
}

variable "private_key" {
  type        = string
  description = "PEM private key for the Terraform service user"
  sensitive   = true
}

variable "service_user_public_keys" {
  type        = map(string)
  description = "RSA public keys per service user (key-pair auth; no passwords for services)"
  default     = {  }
}
