# dodgewuh infrastructure

Terraform creates two Ubuntu 24.04 x86 VMs in us-east-2: a coordinator and a game
worker. Both start as t3.small (4 vCPUs total). Standard CPU credits avoid surplus
credit billing but can throttle sustained workloads; capacity is unmeasured.

The coordinator has a stable Elastic IP and public TCP 80/443. Worker TCP 8000
accepts only the coordinator security group. Both machines have public IPv4 for
outbound Docker downloads and Session Manager, but no SSH ingress. Internal game
traffic uses private IPs. This avoids a NAT gateway; the worker is not in an
isolated private subnet. Two VMs, two root disks, a separate 8 GiB PostgreSQL disk
and public IPv4 incur AWS charges.

```sh
terraform -chdir=infra init
terraform -chdir=infra fmt -check
terraform -chdir=infra validate
terraform -chdir=infra plan -out=dodgewuh.tfplan
```

Review the plan before `terraform -chdir=infra apply dodgewuh.tfplan`. No resources
are created by init, validate or plan. The provider restricts operations to the
expected account. State and saved plans stay local and must not be committed.
The provider lockfile is committed. AMI selection uses Canonical's latest Noble
image; a fresh plan may propose replacement after a newer AMI is published.

## After an approved apply

Use `terraform -chdir=infra output` for the EIP, private worker address, instance
IDs and Session Manager commands. Connect via EC2 console Session Manager or
install the local Session Manager plugin to use `aws ssm start-session`.
Wait for cloud-init and check `sudo cloud-init status --wait` and
`/var/log/cloud-init-output.log`. Bootstrap installs Docker/Compose and enables
SSM; it does not deploy the application or claim Docker installation succeeded
before an actual VM boot.

Build/publish the backend image with an immutable release tag, then place the
appropriate deployment Compose file in /opt/dodgewuh on each host. Put Caddyfile
beside the coordinator Compose file. Supply BACKEND_IMAGE, BUILD_SHA and the same strong GAME_WORKER_SECRET on both;
DOMAIN=dodgewuh.fit and GAME_WORKER_URL from Terraform on the coordinator;
WORKER_PRIVATE_IP from Terraform on the worker. Registry authentication/image
publishing is still to be configured. For example, once those values are set:

```sh
sudo docker compose -f compose.worker.yaml up -d --wait
sudo docker compose -f compose.coordinator.yaml up -d --wait
```

In Porkbun, review/replace only the dodgewuh.fit apex A records with the
coordinator EIP; preserve unrelated records. DNS is manual and unchanged by
Terraform. Caddy obtains TLS after the domain reaches this host. Current Caddy
configuration exposes backend paths and a placeholder root response, not the
frontend. Public health is only an initial infrastructure checkpoint; frontend delivery
and deployed end-to-end gameplay still require verification.

Room allocation, coordinator WebSocket forwarding, shared-secret worker
authentication and worker-loss handling are implemented, including in local
Compose. Keep worker access private and configure the same GAME_WORKER_SECRET
on both services. Frontend hosting is still absent from this deployment
configuration; replace the Caddy placeholder with the matching frontend build
and SPA fallback. Apply migrations through `0003_draw_results` before coordinator
startup. Configuration in Git does not establish deployed acceptance. Neither Compose file uses reload or
source mounts. Deploy/restart between matches; in-memory state will be lost.

## Cleanup

From the repository root, one command removes all Terraform-managed resources:

```sh
terraform -chdir=infra destroy
```

Review the displayed plan and enter `yes`. This deletes both VMs, their root
disks, the PostgreSQL data disk and networking, and releases the Elastic IP.
There is no database destruction guard. Back up any data you want to keep first.
Porkbun DNS is managed manually: remove or restore its A record separately.
Keep the local Terraform state until cleanup completes. Nothing is destroyed by
these instructions alone.

## PostgreSQL data and production secrets

PostgreSQL runs in the coordinator Compose stack, with no exposed database port.
Terraform creates an encrypted independent gp3 volume and attachment; bootstrap
mounts it by volume ID at /opt/dodgewuh/data. Never start PostgreSQL before that
mount is available. The disk survives VM replacement but is deleted by a full
Terraform destroy. VM replacement must
be preceded by a graceful stack shutdown and off-host backup. Restore/re-attach
is restricted to the volume's availability zone.

Create a strong production password file outside the repo and Terraform, e.g.
under root-owned /etc/dodgewuh/secrets (directory 0700, file 0444). Set
POSTGRES_PASSWORD_FILE to its absolute path for production Compose. Both app and
PostgreSQL mount the file; the coordinator reads DB_PASSWORD_FILE and fails startup for missing, unreadable or empty files. Do not
put database passwords in user data, tfvars or image layers. The local example
password must never be reused on EC2. Terraform does not provision credentials
or run migrations; the coordinator reads `DB_PASSWORD_FILE`, and the operator
runs Alembic explicitly before startup.

From the coordinator deployment directory, write a database backup to a protected
operator file, then copy it off-host:

```sh
umask 077
docker compose -f compose.coordinator.yaml exec -T postgres \
  pg_dump -U dodgewuh -d dodgewuh -Fc > dodgewuh.dump
```

Verify a restore into a disposable database before relying on the backup. Never commit SQL dumps. Stop PostgreSQL before a consistent EBS snapshot.
A full Terraform destroy deletes the database disk too. Backups or snapshots
created outside Terraform must be retained or deleted separately.
