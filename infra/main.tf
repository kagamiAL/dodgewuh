data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_vpc" "game" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "dodgewuh" }
}

resource "aws_subnet" "game" {
  vpc_id                  = aws_vpc.game.id
  cidr_block              = "10.42.1.0/24"
  availability_zone       = sort(data.aws_availability_zones.available.names)[0]
  map_public_ip_on_launch = false
  tags                    = { Name = "dodgewuh" }
}

resource "aws_internet_gateway" "game" {
  vpc_id = aws_vpc.game.id
}

resource "aws_route_table" "game" {
  vpc_id = aws_vpc.game.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.game.id
  }
}

resource "aws_route_table_association" "game" {
  subnet_id      = aws_subnet.game.id
  route_table_id = aws_route_table.game.id
}

resource "aws_security_group" "coordinator" {
  name_prefix = "dodgewuh-coordinator-"
  description = "Public HTTP and HTTPS entry point"
  vpc_id      = aws_vpc.game.id
}

resource "aws_security_group" "worker" {
  name_prefix = "dodgewuh-worker-"
  description = "Game traffic from coordinator only"
  vpc_id      = aws_vpc.game.id
}

resource "aws_vpc_security_group_ingress_rule" "web" {
  for_each          = { http = 80, https = 443 }
  security_group_id = aws_security_group.coordinator.id
  ip_protocol       = "tcp"
  from_port         = each.value
  to_port           = each.value
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "worker" {
  security_group_id            = aws_security_group.worker.id
  referenced_security_group_id = aws_security_group.coordinator.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_egress_rule" "outbound" {
  for_each          = { coordinator = aws_security_group.coordinator.id, worker = aws_security_group.worker.id }
  security_group_id = each.value
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

data "aws_iam_policy_document" "ec2_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ssm" {
  name_prefix        = "dodgewuh-ssm-"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.ssm.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ssm" {
  name_prefix = "dodgewuh-ssm-"
  role        = aws_iam_role.ssm.name
}

resource "random_password" "worker_secret" {
  length  = 48
  special = false
}

locals {
  bootstrap = file("${path.module}/../deploy/bootstrap.sh")
  # Values are interpolated into single-quoted shell exports; keep them quote-free.
  common_env = {
    DODGEWUH_REPO      = var.repo_url
    DODGEWUH_REF       = var.git_ref
    GAME_WORKER_SECRET = random_password.worker_secret.result
  }
  worker_env = merge(local.common_env, { DODGEWUH_ROLE = "worker" })
  coordinator_env = merge(local.common_env, {
    DODGEWUH_ROLE           = "coordinator"
    DODGEWUH_DATA_VOLUME_ID = aws_ebs_volume.postgres.id
    DOMAIN                  = var.domain
    GAME_WORKER_URL         = "http://${aws_instance.worker.private_ip}:8000"
  })
}

# Worker and coordinator are separate resources so the coordinator can be given the
# worker's private IP. Changing git_ref (or bootstrap.sh) replaces the instance.
resource "aws_instance" "worker" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.game.id
  vpc_security_group_ids      = [aws_security_group.worker.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.ssm.name
  user_data                   = join("\n", concat(["#!/usr/bin/env bash"], [for k, v in local.worker_env : "export ${k}='${v}'"], [local.bootstrap]))
  user_data_replace_on_change = true
  # A newly published Ubuntu AMI must not replace a running VM; only git_ref/bootstrap changes do.
  lifecycle {
    ignore_changes = [ami]
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }
  root_block_device {
    volume_type           = "gp3"
    volume_size           = 16
    encrypted             = true
    delete_on_termination = true
  }
  credit_specification {
    cpu_credits = var.cpu_credits
  }
  tags       = { Name = "dodgewuh-worker", Role = "worker" }
  depends_on = [aws_route_table_association.game, aws_iam_role_policy_attachment.ssm, aws_vpc_security_group_egress_rule.outbound]
}

resource "aws_instance" "coordinator" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.game.id
  vpc_security_group_ids      = [aws_security_group.coordinator.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.ssm.name
  user_data                   = join("\n", concat(["#!/usr/bin/env bash"], [for k, v in local.coordinator_env : "export ${k}='${v}'"], [local.bootstrap]))
  user_data_replace_on_change = true
  # A newly published Ubuntu AMI must not replace a running VM; only git_ref/bootstrap changes do.
  lifecycle {
    ignore_changes = [ami]
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }
  root_block_device {
    volume_type           = "gp3"
    volume_size           = 16
    encrypted             = true
    delete_on_termination = true
  }
  credit_specification {
    cpu_credits = var.cpu_credits
  }
  tags       = { Name = "dodgewuh-coordinator", Role = "coordinator" }
  depends_on = [aws_route_table_association.game, aws_iam_role_policy_attachment.ssm, aws_vpc_security_group_egress_rule.outbound]
}

resource "aws_eip" "coordinator" {
  domain = "vpc"
  tags   = { Name = "dodgewuh-coordinator" }
}

resource "aws_eip_association" "coordinator" {
  instance_id   = aws_instance.coordinator.id
  allocation_id = aws_eip.coordinator.id
}

# Independent of the VM: reattach on replacement; deleted by terraform destroy.
resource "aws_ebs_volume" "postgres" {
  availability_zone = aws_subnet.game.availability_zone
  size              = var.postgres_volume_size
  type              = "gp3"
  encrypted         = true
  tags              = { Name = "dodgewuh-postgres" }
}

resource "aws_volume_attachment" "postgres" {
  # On redeploy, shut the old coordinator down cleanly (Postgres flushes and stops) before the
  # data volume is detached and moved to the new VM.
  stop_instance_before_detaching = true
  device_name                    = "/dev/sdf"
  volume_id                      = aws_ebs_volume.postgres.id
  instance_id                    = aws_instance.coordinator.id
}
