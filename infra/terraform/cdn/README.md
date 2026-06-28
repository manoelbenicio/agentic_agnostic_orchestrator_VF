# AOP CDN Terraform

This stack provisions the production CDN edge for AOP using AWS CloudFront.

It is intentionally safe to validate without credentials. `terraform plan/apply` requires AWS credentials and a real origin.

## Resources

- CloudFront distribution for AOP web/API traffic.
- No-cache policy for dynamic API paths.
- Static asset cache policy for optional S3-backed `/_next/static/*`.
- Optional Origin Access Control for an S3 static asset bucket.
- Optional aliases, ACM certificate and WAFv2 Web ACL.

## Usage

```bash
cd infra/terraform/cdn
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt -check
terraform validate
terraform plan
```

Do not commit `terraform.tfvars`, state files or generated plans.

## DNS Handoff

Use these outputs when implementing DNS/SSL:

- `distribution_domain_name`
- `hosted_zone_id`
- `distribution_id`

For custom domains, the ACM certificate must exist in `us-east-1`.
