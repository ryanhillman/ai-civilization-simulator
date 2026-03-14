variable "app_name"       { type = string }
variable "app_image"      { type = string }
variable "resource_group" { type = string }
variable "location"       { type = string }
variable "common_env"     { type = map(string) }
variable "secret_env" {
  type      = map(string)
  sensitive = true
}
