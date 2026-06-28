output "distribution_id" {
  description = "CloudFront distribution id."
  value       = aws_cloudfront_distribution.this.id
}

output "distribution_arn" {
  description = "CloudFront distribution ARN."
  value       = aws_cloudfront_distribution.this.arn
}

output "distribution_domain_name" {
  description = "CloudFront generated domain name."
  value       = aws_cloudfront_distribution.this.domain_name
}

output "hosted_zone_id" {
  description = "CloudFront hosted zone id for Route53 alias records."
  value       = aws_cloudfront_distribution.this.hosted_zone_id
}
