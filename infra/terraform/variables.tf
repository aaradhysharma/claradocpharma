variable "aws_region" {
  description = "AWS region for Clara VoiceOps demo resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name prefix for demo resources."
  type        = string
  default     = "clara-voiceops"
}

variable "instance_type" {
  description = "EC2 size for single-node k3s."
  type        = string
  default     = "t3.small"
}

variable "allowed_cidr" {
  description = "CIDR allowed to reach SSH, ArgoCD, and demo NodePort."
  type        = string
  default     = "0.0.0.0/0"
}

variable "ssh_public_key" {
  description = "Public SSH key for the EC2 k3s node."
  type        = string
}
