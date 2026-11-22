variable "name_prefix" {
  type = string
}

variable "folder_id" {
  type = string
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "registry_name" {
  description = "Optional explicit registry name; defaults to <prefix>-cr."
  type        = string
  default     = ""
}
