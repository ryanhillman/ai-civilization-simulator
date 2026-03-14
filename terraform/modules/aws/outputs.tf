output "app_url" {
  description = "HTTPS Function URL of the Lambda."
  value       = aws_lambda_function_url.app.function_url
}

output "ecr_repository_url" {
  description = "ECR repository URL — push the Docker image here before applying."
  value       = aws_ecr_repository.app.repository_url
}
