output "k3s_public_ip" {
  description = "Public IP of the k3s EC2 node."
  value       = aws_instance.k3s.public_ip
}

output "api_ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "worker_ecr_repository_url" {
  value = aws_ecr_repository.worker.repository_url
}

output "web_ecr_repository_url" {
  value = aws_ecr_repository.web.repository_url
}

output "artifact_bucket_name" {
  value = aws_s3_bucket.artifacts.bucket
}
