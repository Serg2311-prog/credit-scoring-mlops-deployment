locals {
  subnet_cidrs = [for s in var.subnets : s.cidr]

  # Admin API ingress only when CIDRs are provided (never 0.0.0.0/0 — validated upstream).
  api_cidrs = var.k8s_api_allowed_cidrs
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

# -----------------------------------------------------------------------------
# Security groups as EMPTY shells — ALL rules via yandex_vpc_security_group_rule.
#
# Root cause (Block 11.9.1): mixing inline ingress/egress on yandex_vpc_security_group
# with a separate yandex_vpc_security_group_rule on the same SG causes the next SG
# update to reconcile ONLY inline rules and DELETE the separately managed rule
# (e.g. "Nodes to master" → worker NOT_CONNECTED).
#
# Cross-SG references stay as rule resources to avoid circular depends_on between
# the two SG resources.
# -----------------------------------------------------------------------------

resource "yandex_vpc_security_group" "k8s_master" {
  folder_id   = var.folder_id
  name        = "${var.name_prefix}-sg-k8s-master"
  description = "Managed Kubernetes master SG (credit-scoring)"
  network_id  = yandex_vpc_network.this.id
  labels      = var.labels

  # Provider 0.250.0: inline ingress/egress and yandex_vpc_security_group_rule are
  # incompatible. Rules are managed only via separate rule resources below.
  # ignore_changes prevents SG Update/Read drift from wiping those rules without
  # requiring manual terraform state push edits during migration.
  lifecycle {
    ignore_changes = [ingress, egress]
  }
}

resource "yandex_vpc_security_group" "k8s_nodes" {
  folder_id   = var.folder_id
  name        = "${var.name_prefix}-sg-k8s-nodes"
  description = "Managed Kubernetes nodes SG (credit-scoring)"
  network_id  = yandex_vpc_network.this.id
  labels      = var.labels

  lifecycle {
    ignore_changes = [ingress, egress]
  }
}

# --- Master rules ----------------------------------------------------------------

resource "yandex_vpc_security_group_rule" "master_self" {
  security_group_binding = yandex_vpc_security_group.k8s_master.id
  direction              = "ingress"
  description            = "Internal cluster communication within this SG"
  protocol               = "ANY"
  from_port              = 0
  to_port                = 65535
  predefined_target      = "self_security_group"
}

resource "yandex_vpc_security_group_rule" "master_lb_healthchecks" {
  security_group_binding = yandex_vpc_security_group.k8s_master.id
  direction              = "ingress"
  description            = "Load balancer health checks (platform predefined)"
  protocol               = "TCP"
  from_port              = 0
  to_port                = 65535
  predefined_target      = "loadbalancer_healthchecks"
}

resource "yandex_vpc_security_group_rule" "master_api_443" {
  count = length(local.api_cidrs) > 0 ? 1 : 0

  security_group_binding = yandex_vpc_security_group.k8s_master.id
  direction              = "ingress"
  description            = "Kubernetes API HTTPS from approved admin CIDRs only"
  protocol               = "TCP"
  port                   = 443
  v4_cidr_blocks         = local.api_cidrs
}

resource "yandex_vpc_security_group_rule" "master_api_6443" {
  count = length(local.api_cidrs) > 0 ? 1 : 0

  security_group_binding = yandex_vpc_security_group.k8s_master.id
  direction              = "ingress"
  description            = "Kubernetes API 6443 from approved admin CIDRs only"
  protocol               = "TCP"
  port                   = 6443
  v4_cidr_blocks         = local.api_cidrs
}

# Critical for node registration — was previously dual-managed and wiped on SG update.
resource "yandex_vpc_security_group_rule" "master_from_nodes" {
  security_group_binding = yandex_vpc_security_group.k8s_master.id
  direction              = "ingress"
  description            = "Nodes to master"
  protocol               = "ANY"
  from_port              = 0
  to_port                = 65535
  security_group_id      = yandex_vpc_security_group.k8s_nodes.id
}

resource "yandex_vpc_security_group_rule" "master_egress" {
  security_group_binding = yandex_vpc_security_group.k8s_master.id
  direction              = "egress"
  description            = "Master egress (control-plane, NTP, metric-server, managed services)"
  protocol               = "ANY"
  from_port              = 0
  to_port                = 65535
  v4_cidr_blocks         = ["0.0.0.0/0"]
}

# --- Node rules ------------------------------------------------------------------

resource "yandex_vpc_security_group_rule" "nodes_self" {
  security_group_binding = yandex_vpc_security_group.k8s_nodes.id
  direction              = "ingress"
  description            = "Node-to-node within SG"
  protocol               = "ANY"
  from_port              = 0
  to_port                = 65535
  predefined_target      = "self_security_group"
}

resource "yandex_vpc_security_group_rule" "nodes_from_master" {
  security_group_binding = yandex_vpc_security_group.k8s_nodes.id
  direction              = "ingress"
  description            = "Master to nodes"
  protocol               = "ANY"
  from_port              = 0
  to_port                = 65535
  security_group_id      = yandex_vpc_security_group.k8s_master.id
}

resource "yandex_vpc_security_group_rule" "nodes_lb_healthchecks" {
  security_group_binding = yandex_vpc_security_group.k8s_nodes.id
  direction              = "ingress"
  description            = "Load balancer health checks (platform predefined)"
  protocol               = "TCP"
  from_port              = 0
  to_port                = 65535
  predefined_target      = "loadbalancer_healthchecks"
}

resource "yandex_vpc_security_group_rule" "nodes_icmp_private" {
  security_group_binding = yandex_vpc_security_group.k8s_nodes.id
  direction              = "ingress"
  description            = "ICMP health checks from Yandex Cloud private ranges"
  protocol               = "ICMP"
  v4_cidr_blocks         = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
}

resource "yandex_vpc_security_group_rule" "nodes_pod_service_cidrs" {
  security_group_binding = yandex_vpc_security_group.k8s_nodes.id
  direction              = "ingress"
  description            = "Pod and Service CIDR traffic (cluster networking)"
  protocol               = "ANY"
  from_port              = 0
  to_port                = 65535
  v4_cidr_blocks         = [var.service_ipv4_range, var.cluster_ipv4_range]
}

resource "yandex_vpc_security_group_rule" "nodes_nodeport" {
  count = var.enable_nodeport_ingress && length(local.api_cidrs) > 0 ? 1 : 0

  security_group_binding = yandex_vpc_security_group.k8s_nodes.id
  direction              = "ingress"
  description            = "Optional NodePort from admin CIDRs only (never 0.0.0.0/0)"
  protocol               = "TCP"
  from_port              = 30000
  to_port                = 32767
  v4_cidr_blocks         = local.api_cidrs
}

resource "yandex_vpc_security_group_rule" "nodes_egress" {
  security_group_binding = yandex_vpc_security_group.k8s_nodes.id
  direction              = "egress"
  description            = "Node egress (registry pulls, OS updates)"
  protocol               = "ANY"
  from_port              = 0
  to_port                = 65535
  v4_cidr_blocks         = ["0.0.0.0/0"]
}
