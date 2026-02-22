# Dolphin Deployment Guide

Production deployment guide for Dolphin as a shared service.
For local development setup, see the project README.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
4. [Process Management](#4-process-management)
5. [Reverse Proxy & TLS](#5-reverse-proxy--tls)
6. [Authentication Hardening](#6-authentication-hardening)
7. [Redis Caching](#7-redis-caching)
8. [Observability](#8-observability)
9. [Health Checks](#9-health-checks)
10. [Upgrading](#10-upgrading)

---

## 1. Prerequisites

| Dependency | Minimum Version | Notes |
|---|---|---|
| Python | 3.12 | 3.13 also supported |
| uv | any | Recommended package manager |
| Bun | 1.x | Required for the MCP bridge |
| OpenAI API key | — | Required for embedding; set in environment |
| Redis | 7.x | Optional; improves cache hit rates across restarts |
| nginx / caddy | any | Recommended for TLS termination and auth proxy |

---

## 2. Installation

```bash
# Install from PyPI
pip install pb-dolphin

# Optional: cross-encoder reranking (~2 GB with torch)
pip install "pb-dolphin[reranking]"

# Verify
dolphin --version
```

With **uv** (recommended for isolated environments):

```bash
uv pip install pb-dolphin
# or, within a project:
uv add pb-dolphin
```

**MCP bridge** (TypeScript):

```bash
cd mcp-bridge
bun install
bun run build
```

---

## 3. Configuration

### 3.1 Initialise the knowledge store

```bash
dolphin init
```

This creates `~/.dolphin/config.toml` from the built-in template and generates an API key stored at `~/.dolphin/kb_api_key`.

For a shared multi-user deployment, point `DOLPHIN_CONFIG_PATH` to a shared location:

```bash
export DOLPHIN_CONFIG_PATH=/etc/dolphin/config.toml
dolphin init
```

### 3.2 Key config settings

Edit `~/.dolphin/config.toml` (or your `DOLPHIN_CONFIG_PATH`):

```toml
[storage]
# Absolute path to avoid ambiguity in production
store_root = "/var/lib/dolphin/knowledge_store"

[server]
# Address the API listens on internally (nginx proxies to this)
endpoint = "127.0.0.1:7777"

[cache]
enabled = true
# Connect to Redis (see §7)
redis_url = "redis://127.0.0.1:6379"

[embedding]
provider = "openai"
api_key_env = "OPENAI_API_KEY"   # name of the env var — not the key itself
```

### 3.3 Environment variables

Dolphin reads from the environment only — it does **not** auto-load `.env` files. Source your env file before starting the server or inject variables via your process manager.

```bash
# Minimal required
export OPENAI_API_KEY="sk-…"

# Override auto-generated API key (optional)
export DOLPHIN_API_KEY="your-secret-key"

# Point to a shared config (optional)
export DOLPHIN_CONFIG_PATH="/etc/dolphin/config.toml"

# Logging
export DOLPHIN_LOG_LEVEL="INFO"          # DEBUG | INFO | WARNING | ERROR
export DOLPHIN_LOG_TRACEBACK="0"         # 1 to include Python tracebacks

# Watcher shutdown grace periods (seconds)
export DOLPHIN_WATCH_SHUTDOWN_TIMEOUT="15"
export DOLPHIN_WATCH_CANCEL_TIMEOUT="5"
```

See `.env.example` at the repo root for the full variable list.

---

## 4. Process Management

### 4.1 systemd (recommended for Linux)

Create `/etc/systemd/system/dolphin.service`:

```ini
[Unit]
Description=Dolphin Knowledge Bank API
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=dolphin
Group=dolphin
WorkingDirectory=/var/lib/dolphin

# Load secrets from a file not committed to version control
EnvironmentFile=/etc/dolphin/env

ExecStart=/usr/local/bin/uvicorn kb.api.server:app_with_lifespan \
    --host 127.0.0.1 \
    --port 7777 \
    --workers 1 \
    --log-level info \
    --no-access-log

Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=dolphin

# Resource limits
LimitNOFILE=65536
MemoryMax=4G

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/var/lib/dolphin

[Install]
WantedBy=multi-user.target
```

`/etc/dolphin/env` (mode `0640`, owned by `root:dolphin`):

```bash
OPENAI_API_KEY=sk-…
DOLPHIN_API_KEY=…
DOLPHIN_CONFIG_PATH=/etc/dolphin/config.toml
DOLPHIN_LOG_LEVEL=INFO
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dolphin
sudo journalctl -u dolphin -f
```

> **Workers**: Dolphin uses SQLite and LanceDB; run **one worker** to avoid write contention. Use the built-in async handling for concurrency.

### 4.2 MCP bridge

Create a companion unit `/etc/systemd/system/dolphin-mcp.service`:

```ini
[Unit]
Description=Dolphin MCP Bridge
After=dolphin.service
Requires=dolphin.service

[Service]
Type=simple
User=dolphin
WorkingDirectory=/opt/dolphin/mcp-bridge
EnvironmentFile=/etc/dolphin/env
ExecStart=/usr/local/bin/bun run dist/index.js
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 4.3 macOS (launchd)

```xml
<!-- ~/Library/LaunchAgents/com.dolphin.api.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>       <string>com.dolphin.api</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/uvicorn</string>
    <string>kb.api.server:app_with_lifespan</string>
    <string>--host</string> <string>127.0.0.1</string>
    <string>--port</string> <string>7777</string>
    <string>--workers</string> <string>1</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OPENAI_API_KEY</key> <string>sk-…</string>
    <key>DOLPHIN_API_KEY</key> <string>…</string>
  </dict>
  <key>RunAtLoad</key>   <true/>
  <key>KeepAlive</key>   <true/>
  <key>StandardOutPath</key> <string>/var/log/dolphin/out.log</string>
  <key>StandardErrorPath</key><string>/var/log/dolphin/err.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.dolphin.api.plist
```

---

## 5. Reverse Proxy & TLS

Run Dolphin on `127.0.0.1:7777` and let the reverse proxy handle TLS termination and public-facing traffic.

### 5.1 nginx

```nginx
# /etc/nginx/sites-available/dolphin
server {
    listen 443 ssl http2;
    server_name kb.example.com;

    ssl_certificate     /etc/ssl/certs/kb.example.com.crt;
    ssl_certificate_key /etc/ssl/private/kb.example.com.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Increase for large indexing payloads
    client_max_body_size 64m;

    location / {
        proxy_pass         http://127.0.0.1:7777;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # Keep-alive for streaming responses
        proxy_set_header   Connection "";
        proxy_read_timeout 300s;
    }

    # Block direct metrics access from the internet
    location /metrics {
        deny all;
    }
}

server {
    listen 80;
    server_name kb.example.com;
    return 301 https://$host$request_uri;
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 5.2 Caddy (automatic TLS)

```caddyfile
# /etc/caddy/Caddyfile
kb.example.com {
    reverse_proxy 127.0.0.1:7777

    # Block Prometheus metrics from public internet
    @metrics path /metrics
    respond @metrics 403

    # Enforce TLS 1.2+
    tls {
        protocols tls1.2 tls1.3
    }
}
```

---

## 6. Authentication Hardening

### 6.1 API key

All requests must include the `X-API-Key` header matching the value stored at `~/.dolphin/kb_api_key` (or `DOLPHIN_API_KEY` if set).

Dolphin uses constant-time comparison (`hmac.compare_digest`) to prevent timing attacks. Keys are **not** logged.

Rotate the key by updating `DOLPHIN_API_KEY` and restarting the service:

```bash
# Generate a new key
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Update /etc/dolphin/env, then:
sudo systemctl restart dolphin
```

### 6.2 Network isolation

- Keep `--host 127.0.0.1` on uvicorn; **never** bind to `0.0.0.0` without a firewall rule.
- Expose only ports 80/443 externally; firewall 7777 to localhost only.

```bash
# ufw example
sudo ufw allow 443/tcp
sudo ufw allow 80/tcp
sudo ufw deny 7777/tcp
```

### 6.3 Rate limiting (nginx)

Add to your nginx config to limit brute-force attempts against the API:

```nginx
# In http {} block
limit_req_zone $binary_remote_addr zone=dolphin_auth:10m rate=10r/m;

# In server {} location block
location /v1/ {
    limit_req zone=dolphin_auth burst=20 nodelay;
    proxy_pass http://127.0.0.1:7777;
    ...
}
```

### 6.4 CORS

The default CORS policy allows `localhost:3000` with specific methods (`GET`, `POST`, `DELETE`, `OPTIONS`) and headers (`X-API-Key`, `Content-Type`, `Accept`). For production, tighten the allowed origins in `kb/api/app.py` to your actual client domain(s).

---

## 7. Redis Caching

Redis is optional but strongly recommended for production. Without it, the cache is in-memory only (bounded to 10,000 entries, lost on restart).

### 7.1 Install Redis

```bash
# Debian/Ubuntu
sudo apt install redis-server
sudo systemctl enable --now redis

# macOS
brew install redis
brew services start redis
```

### 7.2 Configure Dolphin to use Redis

In `config.toml`:

```toml
[cache]
enabled = true
redis_url = "redis://127.0.0.1:6379"
embedding_ttl = 3600   # seconds; 0 = no expiration
result_ttl = 900
```

### 7.3 Redis security

For multi-tenant environments, set a Redis password and restrict bind to localhost:

```
# /etc/redis/redis.conf
bind 127.0.0.1
requirepass "your-redis-password"
```

Update the URL in `config.toml`:

```toml
redis_url = "redis://:your-redis-password@127.0.0.1:6379"
```

---

## 8. Observability

Dolphin ships with a Prometheus + Grafana + Loki stack in `observability/`.

### 8.1 Start the observability stack

```bash
cd observability
cp .env.example .env          # fill in GRAFANA_ADMIN_USER and GRAFANA_ADMIN_PASSWORD
docker compose up -d
```

| Service | Default port | Purpose |
|---|---|---|
| Prometheus | 9090 | Metrics scraping |
| Grafana | 3001 | Dashboards |
| Loki | 3100 | Log aggregation |
| Jaeger | 16686 | Distributed tracing |

### 8.2 Prometheus scrape config

Add a scrape job to `observability/prometheus/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: dolphin
    static_configs:
      - targets: ["127.0.0.1:7777"]
    metrics_path: /metrics
```

The `/metrics` endpoint should remain internal; restrict it at the reverse proxy level (see §5).

### 8.3 Log forwarding

Dolphin writes structured JSON logs to stderr. Promtail (included in the compose stack) tails the systemd journal:

```yaml
# observability/promtail/promtail-config.yml
scrape_configs:
  - job_name: dolphin
    journal:
      labels:
        job: dolphin
      matches: _SYSTEMD_UNIT=dolphin.service
```

---

## 9. Health Checks

```bash
# Quick liveness check (no auth required)
curl http://127.0.0.1:7777/v1/health

# Deep check (backend connectivity, index status)
curl -H "X-API-Key: $DOLPHIN_API_KEY" \
     http://127.0.0.1:7777/v1/health?check=deep
```

Example healthy response:

```json
{
  "status": "ok",
  "version": "0.2.2",
  "backend": "ready",
  "reranking": "disabled"
}
```

For systemd, add a health check to the unit:

```ini
[Service]
ExecStartPost=/bin/sh -c 'for i in 1 2 3 4 5; do sleep 2 && curl -sf http://127.0.0.1:7777/v1/health && exit 0; done; exit 1'
```

---

## 10. Upgrading

```bash
# 1. Pull the new version
pip install --upgrade pb-dolphin
# or with uv:
uv pip install --upgrade pb-dolphin

# 2. Check for config changes
# Compare your config.toml against the updated template:
python -c "import importlib.resources; import kb; print(importlib.resources.files(kb).joinpath('config_template.toml').read_text())"

# 3. Restart
sudo systemctl restart dolphin
sudo systemctl restart dolphin-mcp   # if running the MCP bridge

# 4. Verify
curl http://127.0.0.1:7777/v1/health
```

Schema migrations are applied automatically on startup. A backup of the SQLite database before upgrading is recommended:

```bash
cp /var/lib/dolphin/knowledge_store/meta.db \
   /var/lib/dolphin/knowledge_store/meta.db.bak-$(date +%Y%m%d)
```
