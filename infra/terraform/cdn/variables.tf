variable "aws_region" {
  description = "AWS region for deploy metadata. CloudFront is global; ACM certificates for aliases must be in us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name used for tags and resource names."
  type        = string
  default     = "aop"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "prod"
}

variable "origin_domain_name" {
  description = "DNS name of the origin load balancer, API gateway, or static host. Do not include protocol."
  type        = string

  validation {
    condition     = length(trimspace(var.origin_domain_name)) > 0 && !strcontains(var.origin_domain_name, "://")
    error_message = "origin_domain_name must be a host name without protocol."
  }
}

variable "origin_id" {
  description = "Stable CloudFront origin id."
  type        = string
  default     = "aop-origin"
}

variable "origin_protocol_policy" {
  description = "Protocol policy used by CloudFront when connecting to the origin."
  type        = string
  default     = "https-only"

  validation {
    condition     = contains(["http-only", "https-only", "match-viewer"], var.origin_protocol_policy)
    error_message = "origin_protocol_policy must be http-only, https-only, or match-viewer."
  }
}

variable "origin_http_port" {
  description = "Origin HTTP port."
  type        = number
  default     = 80
}

variable "origin_https_port" {
  description = "Origin HTTPS port."
  type        = number
  default     = 443
}

variable "aliases" {
  description = "Optional custom domain aliases for the distribution."
  type        = list(string)
  default     = []
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN in us-east-1 for aliases. Leave empty to use the default CloudFront certificate."
  type        = string
  default     = ""
}

variable "price_class" {
  description = "CloudFront price class."
  type        = string
  default     = "PriceClass_100"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.price_class)
    error_message = "price_class must be PriceClass_100, PriceClass_200, or PriceClass_All."
  }
}

variable "web_acl_id" {
  description = "Optional AWS WAFv2 Web ACL ARN for CloudFront."
  type        = string
  default     = ""
}

variable "enable_ipv6" {
  description = "Whether to enable IPv6 on the distribution."
  type        = bool
  default     = true
}

variable "comment" {
  description = "CloudFront distribution comment."
  type        = string
  default     = "AOP production CDN"
}

variable "static_bucket_name" {
  description = "Optional S3 bucket name for static assets with Origin Access Control."
  type        = string
  default     = ""
}
