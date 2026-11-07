# dodgewuh deployment runbook — Docker, two EC2 VMs and PostgreSQL

Use [11 persistence](11-sql-persistence.md) as the architecture amendment and
[actual infrastructure instructions](../infra/README.md) for current commands.
Do not create automated tests or test-only dependencies. Use builds, type checks
and manual endpoint/device/multiplayer checks. Earlier systemd-backend, GoDaddy,
no-database and one-VM deployment instructions have been superseded.

## Prepare and review

Region us-east-2; public domain dodgewuh.fit; DNS authority Porkbun. AWS CLI and
Terraform are installed. Use local CLI credentials, never committed secrets.
Terraform provisions two t3.small Ubuntu VMs, private service communication,
coordinator Elastic IP, HTTP/HTTPS ingress, Session Manager administration and an
encrypted persistent PostgreSQL data disk. No inbound SSH or public database port.

```sh
terraform -chdir=infra init
terraform -chdir=infra fmt -check
terraform -chdir=infra validate
terraform -chdir=infra plan -out=dodgewuh.tfplan
```

Review all changes before apply. Preserve the state securely outside Git.
An approved apply creates billable resources; no resources are created by plan.
A full Terraform destroy deletes the PostgreSQL data disk along with the stack.

## Provision and deploy

After approved apply, use Terraform outputs for instance IDs, coordinator EIP and
worker private IP. Connect through Session Manager and verify cloud-init,
Docker/Compose and the coordinator's /opt/dodgewuh/data mount. Consult
/var/log/cloud-init-output.log on bootstrap failure. Do not start PostgreSQL if
the retained EBS disk is not mounted.

Build and publish an immutable backend image; record its SHA and prior image.
Place production Compose/Caddy files on the appropriate host and supply their
required configuration, including the protected PostgreSQL password file. Run
migrations once when implemented, then start worker and coordinator stacks per
infra/README.md. Public application routing, image publishing and migrations are
still implementation work, not guaranteed by Terraform.

In Porkbun, review current apex records and point only dodgewuh.fit to the new
coordinator EIP; preserve unrelated DNS records. Verify public A resolution,
Caddy TLS issuance, /api/health, browser WSS and actual phone sensor permission.
Healthy REST alone does not establish a working match. Run the four-phone match,
role-switch, cancellation, disconnect and two-screen manual acceptance flow in 06.

## Release, backup and rollback

Before VM replacement, stop the coordinator stack and take/copy a database backup
off-host. Apply backward-compatible migrations separately from image startup.
Deploy between matches; restarts end live sessions while SQL history remains.
Rollback to the previous immutable backend image, check schema compatibility,
then verify health and a fresh room manually. A container restart does not roll
back migrations or restore data. Restore backups only through an explicit,
reviewed operation. Never remove the PostgreSQL data path to fix startup.

## Cleanup

Back up any records you want to keep, then run from the repository root:

```sh
terraform -chdir=infra destroy
```

Review the plan and enter `yes`. This removes all Terraform-managed resources,
including PostgreSQL data, root disks and the Elastic IP. There is no disk
protection to disable. Remove or restore the Porkbun A record separately;
Terraform does not manage DNS. Any separately created backups or snapshots also
need their own cleanup decision. Keep state until destruction succeeds.
