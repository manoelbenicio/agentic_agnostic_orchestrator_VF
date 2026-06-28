locals {
  name_prefix       = "${var.project}-${var.environment}"
  has_aliases       = length(var.aliases) > 0
  has_static_bucket = length(trimspace(var.static_bucket_name)) > 0
  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
    Component   = "cdn"
  }
}

resource "aws_cloudfront_origin_access_control" "static_assets" {
  count = local.has_static_bucket ? 1 : 0

  name                              = "${local.name_prefix}-static-oac"
  description                       = "OAC for ${local.name_prefix} static assets"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_cache_policy" "api_no_cache" {
  name        = "${local.name_prefix}-api-no-cache"
  comment     = "No-cache policy for dynamic AOP API routes"
  default_ttl = 0
  max_ttl     = 0
  min_ttl     = 0

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "whitelist"
      headers {
        items = ["Authorization", "Content-Type", "Origin"]
      }
    }
    query_strings_config {
      query_string_behavior = "all"
    }
  }
}

resource "aws_cloudfront_cache_policy" "static_assets" {
  name        = "${local.name_prefix}-static-assets"
  comment     = "Long-lived cache for static AOP assets"
  default_ttl = 86400
  max_ttl     = 31536000
  min_ttl     = 60

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

resource "aws_cloudfront_origin_request_policy" "api_forward_all" {
  name    = "${local.name_prefix}-api-forward-all"
  comment = "Forward API request context to origin"

  cookies_config {
    cookie_behavior = "all"
  }
  headers_config {
    header_behavior = "allExcept"
    headers {
      items = ["Host"]
    }
  }
  query_strings_config {
    query_string_behavior = "all"
  }
}

resource "aws_cloudfront_distribution" "this" {
  enabled         = true
  is_ipv6_enabled = var.enable_ipv6
  comment         = var.comment
  aliases         = var.aliases
  price_class     = var.price_class
  web_acl_id      = var.web_acl_id != "" ? var.web_acl_id : null

  origin {
    domain_name = var.origin_domain_name
    origin_id   = var.origin_id

    custom_origin_config {
      http_port                = var.origin_http_port
      https_port               = var.origin_https_port
      origin_protocol_policy   = var.origin_protocol_policy
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_keepalive_timeout = 5
      origin_read_timeout      = 30
    }
  }

  dynamic "origin" {
    for_each = local.has_static_bucket ? [var.static_bucket_name] : []
    content {
      domain_name              = "${origin.value}.s3.${var.aws_region}.amazonaws.com"
      origin_id                = "aop-static-assets"
      origin_access_control_id = aws_cloudfront_origin_access_control.static_assets[0].id
    }
  }

  default_cache_behavior {
    target_origin_id       = var.origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    compress               = true

    cache_policy_id          = aws_cloudfront_cache_policy.api_no_cache.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.api_forward_all.id
  }

  dynamic "ordered_cache_behavior" {
    for_each = local.has_static_bucket ? [1] : []
    content {
      path_pattern           = "/_next/static/*"
      target_origin_id       = "aop-static-assets"
      viewer_protocol_policy = "redirect-to-https"
      allowed_methods        = ["GET", "HEAD", "OPTIONS"]
      cached_methods         = ["GET", "HEAD", "OPTIONS"]
      compress               = true
      cache_policy_id        = aws_cloudfront_cache_policy.static_assets.id
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn            = local.has_aliases ? var.acm_certificate_arn : null
    cloudfront_default_certificate = local.has_aliases ? false : true
    minimum_protocol_version       = local.has_aliases ? "TLSv1.2_2021" : null
    ssl_support_method             = local.has_aliases ? "sni-only" : null
  }

  tags = local.tags

  lifecycle {
    precondition {
      condition     = !local.has_aliases || length(trimspace(var.acm_certificate_arn)) > 0
      error_message = "acm_certificate_arn is required when aliases are set."
    }
  }
}
