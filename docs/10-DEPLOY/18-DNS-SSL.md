# DNS e SSL

## DNS

Configure o dominio publico em `AOP_DOMAIN` e aponte o DNS para a borda que atende o AOP:

- Sem CDN: registro `A`/`AAAA` para o host que expõe o Nginx.
- Com CDN/CloudFront: `CNAME` para o output `cloudfront_domain_name` da stack Terraform CDN.

Dominios extras podem ser informados em `AOP_ADDITIONAL_DOMAINS`, separados por espaco.

## HTTP padrao

O servico `nginx` continua ativo por padrao para compatibilidade com `ops/start.sh`:

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d nginx
```

Ele atende `NGINX_PORT` e preserva headers `X-Forwarded-*` para API e frontend.

## TLS opt-in

Para validacao local, gere um certificado self-signed:

```bash
ops/generate-nginx-cert.sh
```

Para subir o proxy TLS:

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml --profile tls up -d nginx-tls
```

Em producao, substitua `deploy/nginx/certs/aop.crt` e `deploy/nginx/certs/aop.key` por certificados emitidos por ACME/CA corporativa ou use o certificado ACM da CDN. Chaves e certificados locais ficam ignorados pelo Git.
