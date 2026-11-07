# dodgewuh infrastructure

Terraform creates two Ubuntu 24.04 x86 VMs in us-east-2: a coordinator and a game
worker. Both start as t3.small (4 vCPUs total). Standard CPU credits avoid surplus
credit billing but can throttle sustained workloads; capacity is unmeasured.

The coordinator has a stable Elastic IP and public TCP 80/443. Worker TCP 8000
accepts only the coordinator security group. Both machines have public IPv4 for
outbound Docker downloads and Session Manager, but no SSH ingress. Internal game
traffic uses private IPs. This avoids a NAT gateway; the worker is not in an
isolated private subnet. Two VMs, two disks and public IPv4 incur AWS charges.

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
beside the coordinator Compose file. Supply BACKEND_IMAGE and BUILD_SHA on both;
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
frontend. Public health is the initial deployment checkpoint.

Room allocation, coordinator WebSocket forwarding, worker API authentication,
worker-loss handling and frontend deployment remain unimplemented. Security-group
isolation is present; application authentication between services must be added
before exposing internal control endpoints. Neither Compose file uses reload or
source mounts. Deploy/restart between matches; in-memory state will be lost.

## Cleanup

Save evidence/source, remove or restore the changed Porkbun record, review
`terraform -chdir=infra plan -destroy`, then explicitly approve destruction.
Confirm termination, disk deletion and EIP release in AWS. Never run destroy
against a state file you have not reviewed.
