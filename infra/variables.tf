variable "region" {
  type    = string
  default = "us-east-2"
}

variable "account_id" {
  type    = string
  default = "127471246523"
}

variable "domain" {
  type    = string
  default = "dodgewuh.fit"
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "postgres_volume_size" {
  description = "GiB for the retained encrypted PostgreSQL data disk"
  type        = number
  default     = 8
  validation {
    condition     = var.postgres_volume_size >= 8 && floor(var.postgres_volume_size) == var.postgres_volume_size
    error_message = "PostgreSQL data disk must be an integer of at least 8 GiB."
  }
}
