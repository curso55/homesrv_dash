# Dashy dashboard config

Replaced [gethomepage/homepage](https://gethomepage.dev) as the homelab dashboard
on 2026-08-23. Live at `https://dash.area52.lan`.

`conf.yml` and `dark.css` in this directory are symlinks into
`~/homesrv_webstack/dashy/` — the real files live there (next to the rest of
the webstack's Docker Compose project) and are just mirrored here for
version control. Edit them in place on homesrv; git will pick up the change
through the symlink.

## What's NOT in this repo

- **`dashy.env`** — holds `DASHY_PIHOLE_API_KEY` / `DASHY_UPTIME_KUMA_API_KEY`.
  Lives only at `~/homesrv_webstack/dashy/dashy.env`, mode `600`, never
  committed. (Both keys are currently unused — see "Known Dashy bugs" below.)
- **`docker-compose.yml`** and **`Caddyfile`** — shared by every service in
  the webstack, not Dashy-specific. The relevant pieces are documented below
  so this directory is self-contained enough to redeploy from.

## Deployment

### `docker-compose.yml` service block

```yaml
  dashy:
    image: lissy93/dashy:latest
    container_name: dashy
    ports:
      - "3000:8080"
    env_file:
      - ./dashy/dashy.env
    environment:
      - NODE_EXTRA_CA_CERTS=/app/user-data/caddy_root.crt
    volumes:
      - ./dashy/conf.yml:/app/user-data/conf.yml
      - ./dashy/dark.css:/app/user-data/dark.css
      - /home/curso/caddy_root.crt:/app/user-data/caddy_root.crt:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "node", "/app/services/healthcheck.js"]
      interval: 1m30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

The `caddy_root.crt` mount + `NODE_EXTRA_CA_CERTS` are required for Dashy's
server-side status-check pings against `https://*.area52.lan` tiles — without
it every HTTPS status dot fails with "unable to get issuer cert locally",
since Caddy's internally-issued cert isn't in Node's default trust store.

### Caddy site block

```caddyfile
dash.area52.lan {
	import local_tls
	reverse_proxy dashy:8080
}
```

### After editing `conf.yml` or `dark.css`

```bash
cd ~/homesrv_webstack && docker compose up -d --force-recreate dashy
```

(`restart` alone is not enough after volumes/env change; `--force-recreate`
also dodges the bind-mount-stale-inode issue.)

## Custom widgets

Two sections use Dashy's `embed` widget type (raw HTML/CSS/JS) instead of a
built-in widget, since neither exists natively in Dashy:

- **Docker Containers** — polls Glances' `/api/4/containers` endpoint
  (`http://192.168.2.245:61208`) every 10s client-side. Fully live: new/removed
  containers just appear on the next poll, no config changes needed.
- **System Info** (neofetch-style) — OS/Kernel/CPU/Packages/Shell are
  **hardcoded** in the widget's `script` block, because Glances only reports
  *its own container's* `/etc/os-release` (Alpine), not the real Ubuntu host.
  Uptime/Memory/Disk/container-count are still pulled live from Glances. If
  homesrv's kernel or Ubuntu version ever changes, update the `STATIC` object
  in that widget's script manually.

Both depend on Glances (`192.168.2.245:61208`) being reachable from the
browser — same requirement as the System Vitals widgets.

## Known Dashy bugs (as of image `lissy93/dashy:latest`, v4.6.0)

Two widgets were dropped from the live dashboard (kept as plain link tiles
with a status-check dot instead) because of confirmed bugs in Dashy itself,
not misconfiguration:

- **`pi-hole-stats-v6`**: when routed through Dashy's own CORS proxy (required
  for the `DASHY_*` env-var secret substitution to work), the client
  pre-stringifies the auth POST body without setting `Content-Type`, so
  Dashy's server can't parse it and forwards an empty body. Pi-hole then
  rejects it: `"No password found in JSON payload"`.
- **`uptime-kuma`**: the widget base64-encodes the API key into the
  `Authorization` header *client-side*, before the request ever reaches
  Dashy's server-side env-var substitution. The literal placeholder string
  (`DASHY_UPTIME_KUMA_API_KEY`) gets encoded and sent as-is — confirmed via
  Uptime Kuma's own logs showing real `invalid API Key` rejections.

Both are fixable by dropping `useProxy` and putting the real key directly in
`conf.yml` as plaintext instead — declined for now to keep secrets out of the
config file. Worth re-testing after a Dashy version bump.
