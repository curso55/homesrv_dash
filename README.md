# homesrv webstack

Config-as-code for the Docker Compose stack running on `homesrv`
(192.168.2.245) — Caddy reverse proxy fronting every internal `*.area52.lan`
service, plus the Dashy dashboard, Uptime Kuma, MySpeed, and Glances.

Runtime data (`data/`, `config/`) and secrets (`dashy/dashy.env`) are
git-ignored — see `.gitignore`. This repo holds the actual config files the
running containers mount, not copies, so edits here are edits to the live
setup.

## Layout

- **`Caddyfile`** — reverse proxy routing for every `*.area52.lan` subdomain
- **`docker-compose.yml`** — the stack itself (Caddy, Dashy, Uptime Kuma,
  MySpeed, Glances)
- **`dashy/`** — Dashy dashboard config; see `dashy/README.md` for deployment
  details, custom widgets, and known upstream Dashy bugs
- **`scripts/`** — `factorio_status.py` / `update_check.py`, leftover from the
  old Homepage dashboard's custom widgets. No longer wired to cron (the jobs
  errored after Homepage's config dir was removed) — kept for reference only
- **`dashboard-cli/`** — a standalone terminal system-info tool (ANSI-colored
  CLI output), unrelated to the web dashboard or any of the above; run
  manually, not a service

## Deploying a change

```bash
cd ~/homesrv_webstack
docker compose up -d --force-recreate <service>
```

`restart` alone doesn't pick up bind-mount or env changes reliably — see
`dashy/README.md` for the specific gotcha with edited config files pinning to
a stale inode.
