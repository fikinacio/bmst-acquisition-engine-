#!/usr/bin/env bash
# BMST Acquisition Engine — production deploy script
# Run from the project root on the VPS:  bash deploy.sh
set -euo pipefail

DOMAIN="api.biscaplus.com"
NGINX_CONF="/etc/nginx/sites-available/${DOMAIN}.conf"

echo "=== [1/5] Verificar .env ==="
if [ ! -f .env ]; then
  echo "ERRO: .env não encontrado. Copia .env.example para .env e preenche os valores."
  exit 1
fi
echo "OK"

echo "=== [2/5] Build e arranque do container ==="
docker compose pull --quiet || true
docker compose build
docker compose up -d
echo "Container bmst-api a correr na porta 8080 (loopback)"

echo "=== [3/5] Configurar nginx ==="
if [ ! -f "$NGINX_CONF" ]; then
  cp nginx/api.biscaplus.com.conf "$NGINX_CONF"
  ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
  echo "Configuração nginx copiada"
else
  echo "Configuração nginx já existe, a saltar"
fi

echo "=== [4/5] Certificado SSL (Let's Encrypt) ==="
if [ ! -d "/etc/letsencrypt/live/${DOMAIN}" ]; then
  echo "A obter certificado para ${DOMAIN}..."
  # Teste sem --nginx para garantir que o bloco HTTP já está activo
  nginx -t && systemctl reload nginx
  certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos \
    --email contact@biscaplus.com --redirect
  echo "Certificado obtido"
else
  echo "Certificado já existe, a saltar"
fi

echo "=== [5/5] Recarregar nginx e verificar saúde ==="
nginx -t
systemctl reload nginx

sleep 3
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${DOMAIN}/health" || echo "000")
if [ "$STATUS" = "200" ]; then
  echo ""
  echo "====================================="
  echo " Deploy concluído com sucesso!"
  echo " FastAPI acessível em: https://${DOMAIN}"
  echo "====================================="
else
  echo "AVISO: /health devolveu HTTP ${STATUS} — verifica os logs:"
  echo "  docker logs bmst-api --tail 50"
fi
