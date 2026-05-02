data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

resource "aws_key_pair" "demo" {
  key_name   = "${var.project_name}-key"
  public_key = var.ssh_public_key
}

resource "aws_ecr_repository" "api" {
  name                 = "${var.project_name}/api"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "worker" {
  name                 = "${var.project_name}/worker"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "web" {
  name                 = "${var.project_name}/web"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_s3_bucket" "artifacts" {
  bucket_prefix = "${var.project_name}-artifacts-"
}

resource "aws_security_group" "k3s" {
  name        = "${var.project_name}-k3s"
  description = "Single-node k3s demo access"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }

  ingress {
    description = "Kubernetes API"
    from_port   = 6443
    to_port     = 6443
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }

  ingress {
    description = "Clara web NodePort"
    from_port   = 30080
    to_port     = 30080
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "k3s" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  key_name                    = aws_key_pair.demo.key_name
  vpc_security_group_ids      = [aws_security_group.k3s.id]
  associate_public_ip_address = true

  user_data = <<-EOF
    #!/usr/bin/env bash
    set -euxo pipefail
    apt-get update
    apt-get install -y curl git
    curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644
    kubectl create namespace argocd || true
    kubectl create namespace clara-voiceops || true
  EOF

  tags = {
    Name    = "${var.project_name}-k3s"
    Project = var.project_name
  }
}
