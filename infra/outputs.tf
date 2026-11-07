output "coordinator_public_ip" {
  value = aws_eip.coordinator.public_ip
}
output "worker_private_ip" {
  value = aws_instance.server["worker"].private_ip
}
output "game_worker_url" {
  value = "http://${aws_instance.server["worker"].private_ip}:8000"
}
output "public_origin" {
  value = "https://${var.domain}"
}
output "instance_ids" {
  value = { for role, instance in aws_instance.server : role => instance.id }
}
output "session_commands" {
  value = { for role, instance in aws_instance.server : role => "aws ssm start-session --region ${var.region} --target ${instance.id}" }
}
