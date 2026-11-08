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

variable "cpu_credits" {
  description = "t3 CPU credit mode. unlimited avoids throttling to 20% CPU during builds and matches; standard caps cost."
  type        = string
  default     = "unlimited"
  validation {
    condition     = contains(["standard", "unlimited"], var.cpu_credits)
    error_message = "cpu_credits must be standard or unlimited."
  }
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

variable "repo_url" {
  description = "Public Git repository the instances clone at boot"
  type        = string
  default     = "https://github.com/kagamiAL/eggwuh-htc-2026.git"
}

variable "git_ref" {
  description = "Commit SHA to deploy (must be pushed). Changing it replaces both instances."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.git_ref))
    error_message = "git_ref must be a full 40-character commit SHA."
  }
}
