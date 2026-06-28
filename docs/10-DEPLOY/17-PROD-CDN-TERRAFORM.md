# 17 — Produção: CDN e Terraform

Task SS adiciona a base versionável em `infra/terraform/cdn`.

## Escopo

- CDN global via AWS CloudFront.
- Origem configurável por DNS (`origin_domain_name`).
- HTTPS obrigatório para viewers.
- TLS 1.2 para a origem.
- Política sem cache para tráfego dinâmico/API.
- Cache longo opcional para assets estáticos `/_next/static/*` via bucket S3 com Origin Access Control.
- Aliases, ACM e WAF opcionais por variável.

## Validação Local

```bash
terraform -chdir=infra/terraform/cdn fmt -check -recursive
terraform -chdir=infra/terraform/cdn init -backend=false
terraform -chdir=infra/terraform/cdn validate
```

O CI executa `terraform fmt -check` quando o binário `terraform` está disponível no runner.

## Aplicação

```bash
cd infra/terraform/cdn
cp terraform.tfvars.example terraform.tfvars
# editar origem, aliases e ACM
terraform init
terraform plan
terraform apply
```

Não commitar `terraform.tfvars`, state ou planos.
