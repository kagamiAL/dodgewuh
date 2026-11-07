# Deployment runbook — single EC2 working MVP

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

Alan owns this runbook's implementation. Commands describe future artifacts that Alan must create; nothing has been provisioned by this planning task. Use one EC2 Linux instance, one Elastic IP, EBS root disk, security group and simple public network. Caddy serves the built frontend and proxies FastAPI on loopback. GoDaddy remains DNS authority. No database, Redis, containers, CloudFront, API Gateway, load balancer or ACM required.

## Prerequisites and evidence

Confirm AWS credentials/region/quota, GoDaddy DNS access, existing key pair and a suitable Ubuntu 24.04 x86_64 AMI in the chosen region. Start with t3.small, 16 GiB gp3 root, IMDSv2 required, encrypted root disk; these are proposed sizes, not benchmark results or a free-tier claim. Choose the closest available region to the venue. Free domain does not mean free EC2/EBS/public IPv4.

Official sources checked 2026-11-07:

- [AWS security-group rules](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html): allow TCP 80/443 publicly and SSH only from operator CIDR. Do not expose 8000 or 5173.
- [Terraform AWS EIP resource](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/eip): VPC Elastic IP allocation supported; use domain=vpc and explicit instance association.
- [GoDaddy A record instructions](https://www.godaddy.com/help/add-an-a-record-19238): chosen hostname must point to EIP in the authoritative zone.
- [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https) and [reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy): certificate automation and WebSocket tunnelling supported.

Actual domain ownership, DNS propagation, EC2 capacity and certificate issuance remain untested. Use the runbook smoke gate to verify them; do not report deployment success from Terraform alone.

## Infrastructure files and variables

infra/versions.tf pins tested Terraform/provider compatibility and commits .terraform.lock.hcl. Use standard aws provider; no GoDaddy provider dependency. main.tf creates a small VPC, public subnet, internet gateway, route table/association, security group, EC2 instance, EIP and association. Avoid assuming a default VPC exists. Use one module (root), not a hierarchy. variables.tf requires region, ami_id, instance_type (default t3.small), key_name, operator_cidr, domain; tags include project and owner. outputs.tf emits public_ip, domain and ssh command. bootstrap user data installs Python venv support and Caddy via its official package repository, creates a non-login dodgewuh user and /opt/dodgewuh/releases. No AWS secrets in user data; no runtime AWS permissions required. deploy/bootstrap.sh must be idempotent and fail visibly if package install fails.

```sh
export AWS_PROFILE=hackathon
export AWS_REGION=ca-central-1
export DOMAIN=game.YOUR-DOMAIN.example
aws sts get-caller-identity
terraform -chdir=infra init
terraform -chdir=infra fmt -check
terraform -chdir=infra validate
terraform -chdir=infra plan -out=tfplan
terraform -chdir=infra apply tfplan
terraform -chdir=infra output -raw public_ip
```

Set actual variables in uncommitted terraform.tfvars or TF_VAR_* before plan; DOMAIN alone does not set TF_VAR_domain. Explicitly set `export TF_VAR_domain="$DOMAIN"` and region equivalently. Keep state local on Alan's encrypted laptop for this event, back it up securely, and never commit state/tfplan/tfvars or private keys. No shared remote-state service needed for one operator.

## DNS and ports

In GoDaddy DNS for the actual domain: add A record Name `game` (or chosen host), Value Terraform public_ip, shortest available practical TTL. For apex use @. Remove conflicting A records for that host and stale AAAA if IPv6 is not configured; leave unrelated mail/domain records intact. Confirm nameservers are GoDaddy-managed; otherwise change the actual authoritative DNS zone. Do not use GoDaddy URL forwarding. Wait until public resolvers return EIP:

```sh
dig +short A "$DOMAIN"
dig +short AAAA "$DOMAIN"
```

Security group and instance firewall allow TCP 80/443 from internet, 22 from operator_cidr only. Public subnet has route to internet gateway. Outbound DNS/HTTPS and package fetch traffic must work (default allow outbound acceptable for MVP). Caddy needs domain reachability for certificate challenges. Restrictive CAA records may block issuance; inspect them before repeated retries.

## Services and proxy

Alan creates deploy/Caddyfile with the following shape. Keep path prefixes: use handle, not handle_path.

```caddyfile
{$DOMAIN} {
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /ws/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        root * /opt/dodgewuh/current/frontend/dist
        try_files {path} /index.html
        file_server
    }
    log
}
```

Provide DOMAIN to the Caddy systemd service via a drop-in EnvironmentFile=/etc/dodgewuh/caddy.env; a shell export alone does not reach systemd. Persist Caddy's certificate storage across releases; do not delete it during deploy. SPA fallback applies only to frontend, never /api or /ws.

Backend systemd unit: User=dodgewuh, WorkingDirectory=/opt/dodgewuh/current/backend, EnvironmentFile=/etc/dodgewuh/backend.env, ExecStart=/opt/dodgewuh/current/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1, Restart=on-failure, WantedBy=multi-user.target. Never --reload or multiple workers. Environment: PUBLIC_ORIGIN=https://actual-host, LOG_LEVEL=INFO, BUILD_SHA=release SHA, ROOM_LIMIT=10. No gameplay constants in environment. Restrict env files to service/operator access.

Install unit and Caddyfile, then:

```sh
sudo systemctl daemon-reload
sudo env DOMAIN="$DOMAIN" caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now dodgewuh caddy
sudo systemctl restart dodgeball
sudo systemctl reload caddy
```

For manual `caddy validate`, supply DOMAIN in that command's environment (for example `sudo env DOMAIN="$DOMAIN" caddy validate --config /etc/caddy/Caddyfile`); the unit environment is only used by service operations. Certificate issuance may happen after service starts; inspect journal before retrying.

## Build and release

Build locally from clean commit using pinned dependencies. deploy/deploy.sh is an implementation task with this exact CLI contract:

```sh
cd frontend
npm ci
npm run typecheck
npm run build
cd ..
export DEPLOY_HOST="$(terraform -chdir=infra output -raw public_ip)"
export RELEASE_SHA="$(git rev-parse --short HEAD)"
./deploy/deploy.sh "$DEPLOY_HOST" "$RELEASE_SHA"
```

Script must upload backend, requirements.lock and frontend/dist into /opt/dodgewuh/releases/$RELEASE_SHA using SSH/SCP, create release .venv on EC2, install locked requirements, set ownership/read permissions for dodgewuh and Caddy, and validate import before activation. Save prior symlink target, atomically replace current symlink, restart backend, reload Caddy only if config changed, curl health, and revert symlink/restart on failed health. Source .git, secrets, node_modules and Terraform state never belong in release. A backend restart loses rooms and Caddy config reload can close WebSockets: deploy/reload between matches and tell participants to create a new room. Retain two known-good release directories.

## Smoke, logs, rollback

```sh
curl --fail "https://$DOMAIN/api/health"
curl --fail -X POST "https://$DOMAIN/api/rooms" -H 'Content-Type: application/json' -d '{"name":"Deployment smoke"}'
sudo journalctl -u dodgeball -n 100 --no-pager
sudo journalctl -u caddy -n 100 --no-pager
sudo systemctl status dodgewuh caddy
```

Run journal/systemctl on EC2. Do not copy token-bearing creation response into shared logs. Open page on phone cellular data, verify valid certificate and WSS 101, authenticate via app, observe snapshots for ten minutes, then four-phone match. Log room IDs, build SHA, input rejection counts, tick overruns, snapshot queue drops and disconnect reasons, never tokens/raw sensors. Keep logs bounded by journald limits; no monitoring service needed.

Rollback: identify prior /opt/dodgewuh/releases/SHA, `sudo ln -sfn /opt/dodgewuh/releases/PREVIOUS_SHA /opt/dodgewuh/current.next`, then `sudo mv -Tf /opt/dodgewuh/current.next /opt/dodgewuh/current`, restart dodgeball and health-check. Replace PREVIOUS_SHA with actual known-good release. Restore old Caddyfile only if it changed, validate and reload. Rollback also loses rooms; create a fresh one. If health passes but assets fail, inspect Caddy permissions and frontend/dist path. 404 on WS: verify /ws prefix preserved. 403/4401: inspect Origin/token, not certificate settings. Socket drops: confirm one worker and no deployment/reload during match.

## Independent local HTTPS

Backend and Vite work locally per [04](04-repository-structure.md). For actual phones without AWS, run Caddy on developer machine using a local hostname resolving to LAN IP and `tls internal`, proxy /api and /ws to 8000 and other paths to Vite 5173. Explicitly allow hostname in Vite and PUBLIC_ORIGIN. Install the Caddy local root CA profile on each test iPhone and enable full trust in device certificate settings; verify HTTPS trusted before testing sensors. LAN name resolution and CA trust are manual setup prerequisites. Never assume LAN HTTP enables sensors. Remove test trust after event. This mode is independent of public DNS/AWS; avoid spending more than 30 minutes on it if public HTTPS is already working.

## Cleanup and cost

Save demo recording/results and desired source before cleanup. Delete temporary GoDaddy A record or restore previous value, then `terraform -chdir=infra plan -destroy` and `terraform -chdir=infra destroy`. Confirm EC2 terminated, root volume deleted, EIP released, and no orphan resources remain. Check billing console; public IPv4, EC2 and EBS may incur charges even with a free domain. Do not promise a price without checking the actual account/region. Remove temporary SSH keys/phone CA profiles, revoke temporary credentials and securely handle retained state. Domain renewal is separate from Terraform.
