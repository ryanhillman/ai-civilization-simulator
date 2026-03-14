# =============================================================================
# AWS Lambda (container image) + Function URL — Scale-to-Zero
#
# Resources created:
#   - ECR Repository               (stores the container image)
#   - IAM Role + Policy            (Lambda execution role)
#   - SSM Parameter Store secrets  (one per sensitive var)
#   - Lambda Function              (container image, 512 MB, 30s timeout)
#   - Lambda Function URL          (public HTTPS endpoint, no API GW cost)
#
# Scale-to-zero model:
#   Lambda bills only for invocation duration — $0 when idle.
#   The AWS Lambda Web Adapter (baked into the Dockerfile) translates
#   Lambda invocation payloads into plain HTTP, so uvicorn runs unchanged.
#
# PostgreSQL connection note:
#   Lambda re-uses execution environments across warm invocations but does
#   not maintain long-lived connection pools between cold starts.
#   For production workloads consider adding AWS RDS Proxy (not included
#   here to keep the showcase minimal).
# =============================================================================

# --- ECR repository (the GitHub Action pushes the image here first) ---
resource "aws_ecr_repository" "app" {
  name                 = var.app_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true   # allows `terraform destroy` to clean up

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- IAM: Lambda execution role ---
resource "aws_iam_role" "lambda" {
  name = "${var.app_name}-lambda-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "LambdaAssumeRole"
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Allow Lambda to read SSM parameters (for secrets)
resource "aws_iam_role_policy" "ssm_read" {
  name = "${var.app_name}-ssm-read"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter", "ssm:GetParameters"]
      Resource = "arn:aws:ssm:${var.aws_region}:*:parameter/${var.app_name}/*"
    }]
  })
}

# --- SSM Parameter Store: sensitive env vars ---
resource "aws_ssm_parameter" "secrets" {
  for_each = var.secret_env
  name     = "/${var.app_name}/${each.key}"
  type     = "SecureString"
  value    = each.value
}

# --- Lambda Function ---
resource "aws_lambda_function" "app" {
  function_name = var.app_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = var.app_image
  timeout       = 30    # seconds; increase for slow cold starts
  memory_size   = 512   # MB

  environment {
    # Merge plain env vars with resolved secrets.
    # SSM SecureString values are fetched at function init via the SDK
    # in a real production setup; for this showcase they are passed directly
    # so the app env matches local behaviour without extra init code.
    variables = merge(
      var.common_env,
      { for k, v in var.secret_env : k => v }
    )
  }

  depends_on = [aws_iam_role_policy_attachment.lambda_basic]
}

# --- Lambda Function URL (public HTTPS endpoint, replaces API Gateway) ---
resource "aws_lambda_function_url" "app" {
  function_name      = aws_lambda_function.app.function_name
  authorization_type = "NONE"   # public — add "AWS_IAM" for private deployments

  cors {
    allow_credentials = false
    allow_origins     = ["*"]
    allow_methods     = ["*"]
    allow_headers     = ["content-type", "x-amz-date", "authorization"]
    max_age           = 86400
  }
}
