locals {
  subnet_cidrs = [for s in var.subnets : s.cidr]
}

# Soft uniqueness check: Terraform cannot fully prove CIDR non-overlap,
# but duplicate exact CIDRs are rejected.
resource "terraform_data" "cidr_unique" {
  input = local.subnet_cidrs

  lifecycle {
    precondition {
      condition     = length(local.subnet_cidrs) == length(distinct(local.subnet_cidrs))
      error_message = "Subnet CIDRs must be unique; overlapping ranges must be reviewed manually."
    }
  }
}

resource "yandex_vpc_network" "this" {
  folder_id   = var.folder_id
  name        = "${var.name_prefix}-net"
  description = var.network_description
  labels      = var.labels
}

resource "yandex_vpc_subnet" "this" {
  for_each = { for s in var.subnets : s.name => s }

  folder_id      = var.folder_id
  name           = "${var.name_prefix}-subnet-${each.value.name}"
  description    = "Subnet ${each.value.name} for ${var.name_prefix}"
  zone           = each.value.zone
  network_id     = yandex_vpc_network.this.id
  v4_cidr_blocks = [each.value.cidr]
  labels         = var.labels

  depends_on = [terraform_data.cidr_unique]
}

# Master security group: no SSH; API only from explicit admin CIDRs.
resource "yandex_vpc_security_group" "k8s_master" {
  folder_id   = var.folder_id
  name        = "${var.name_prefix}-sg-k8s-master"
  description = "Managed Kubernetes master SG (credit-scoring)"
  network_id  = yandex_vpc_network.this.id
  labels      = var.labels

  ingress {
    description       = "Internal cluster communication within this SG"
    protocol          = "ANY"
    predefined_target = "self_security_group"
    from_port         = 0
    to_port           = 65535
  }

  dynamic "ingress" {
    for_each = length(var.k8s_api_allowed_cidrs) > 0 ? [1] : []
    content {
      description    = "Kubernetes API from approved admin CIDRs only"
      protocol       = "TCP"
      port           = 443
      v4_cidr_blocks = var.k8s_api_allowed_cidrs
    }
  }

  egress {
    description    = "Master egress (control-plane managed services)"
    protocol       = "ANY"
    from_port      = 0
    to_port        = 65535
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}

# Node security group: no public SSH; NodePort optional and CIDR-restricted.
resource "yandex_vpc_security_group" "k8s_nodes" {
  folder_id   = var.folder_id
  name        = "${var.name_prefix}-sg-k8s-nodes"
  description = "Managed Kubernetes nodes SG (credit-scoring)"
  network_id  = yandex_vpc_network.this.id
  labels      = var.labels

  ingress {
    description       = "Node-to-node within SG"
    protocol          = "ANY"
    predefined_target = "self_security_group"
    from_port         = 0
    to_port           = 65535
  }

  ingress {
    description       = "Master to nodes"
    protocol          = "ANY"
    security_group_id = yandex_vpc_security_group.k8s_master.id
    from_port         = 0
    to_port           = 65535
  }

  dynamic "ingress" {
    for_each = var.enable_nodeport_ingress && length(var.k8s_api_allowed_cidrs) > 0 ? [1] : []
    content {
      description    = "Optional NodePort from admin CIDRs (prefer Ingress/LB later)"
      protocol       = "TCP"
      from_port      = 30000
      to_port        = 32767
      v4_cidr_blocks = var.k8s_api_allowed_cidrs
    }
  }

  # Image pulls / OS updates. Production hardening: NAT + private endpoints later.
  egress {
    description    = "Node egress (registry pulls, OS updates) — tighten with NAT/endpoints later"
    protocol       = "ANY"
    from_port      = 0
    to_port        = 65535
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}

# Cross-link: allow nodes to talk to master SG.
resource "yandex_vpc_security_group_rule" "master_from_nodes" {
  security_group_binding = yandex_vpc_security_group.k8s_master.id
  direction              = "ingress"
  description            = "Nodes to master"
  protocol               = "ANY"
  from_port              = 0
  to_port                = 65535
  security_group_id      = yandex_vpc_security_group.k8s_nodes.id
}
