output "network_id" {
  description = "VPC network ID."
  value       = yandex_vpc_network.this.id
}

output "subnet_ids" {
  description = "Map of subnet name → subnet ID."
  value       = { for k, s in yandex_vpc_subnet.this : k => s.id }
}

output "subnet_ids_list" {
  description = "Ordered list of subnet IDs (module input order)."
  value       = [for s in var.subnets : yandex_vpc_subnet.this[s.name].id]
}

output "subnet_zones" {
  description = "Map of subnet name → zone."
  value       = { for k, s in yandex_vpc_subnet.this : k => s.zone }
}

output "master_security_group_id" {
  description = "Security group ID for Kubernetes master."
  value       = yandex_vpc_security_group.k8s_master.id
}

output "nodes_security_group_id" {
  description = "Security group ID for Kubernetes nodes."
  value       = yandex_vpc_security_group.k8s_nodes.id
}

output "security_group_rule_ids" {
  description = "All managed SG rule IDs (create-before cluster; destroy-after cluster)."
  value = compact(concat(
    [
      yandex_vpc_security_group_rule.master_self.id,
      yandex_vpc_security_group_rule.master_lb_healthchecks.id,
      yandex_vpc_security_group_rule.master_from_nodes.id,
      yandex_vpc_security_group_rule.master_egress.id,
      yandex_vpc_security_group_rule.nodes_self.id,
      yandex_vpc_security_group_rule.nodes_from_master.id,
      yandex_vpc_security_group_rule.nodes_lb_healthchecks.id,
      yandex_vpc_security_group_rule.nodes_icmp_private.id,
      yandex_vpc_security_group_rule.nodes_pod_service_cidrs.id,
      yandex_vpc_security_group_rule.nodes_egress.id,
    ],
    yandex_vpc_security_group_rule.master_api_443[*].id,
    yandex_vpc_security_group_rule.master_api_6443[*].id,
    yandex_vpc_security_group_rule.nodes_nodeport[*].id,
  ))
}
