# Deploying dodgewuh

One `terraform apply` creates two VMs in AWS (us-east-2). On first boot each VM clones this
repo at the commit you choose, builds its Docker images, runs migrations and starts itself.
You set one variable (`git_ref`) and one DNS record. Nothing else is done by hand.

```
browser / phones ──HTTPS──▶ coordinator VM  (Elastic IP — never changes)
                              caddy → serves the frontend, proxies /api and /ws
                              coordinator → rooms and registration
                              postgres → on a separate disk that survives redeploys
                                   │ private network
                                   ▼
                            worker VM  (not reachable from the internet)
                              game-worker → live matches
```

**Run every command from the repository root.**

---

## One-time setup

Do this once per laptop. **Only one laptop should ever run `terraform apply`** (see
[Terraform state](#terraform-state)).

1. Install **Terraform ≥ 1.10**, the **AWS CLI v2** and **Docker**.
2. Install the **AWS Session Manager plugin**, which gives you a shell on the VMs (there's no SSH):
   https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html
3. Sign in to AWS and confirm you're in the right account:
   ```sh
   aws sts get-caller-identity --query Account --output text
   # must print: 127471246523
   ```
4. Initialise Terraform:
   ```sh
   terraform -chdir=infra init
   ```

---

## Fresh deploy

Use this when nothing is deployed yet. It takes about 30 minutes, mostly waiting.

### 1. Push the exact commit you want to ship

The VMs download the code from GitHub, so **anything not pushed won't be deployed.**

```sh
git status                    # must be clean
git push origin main
export TF_VAR_git_ref=$(git rev-parse HEAD)
git ls-remote origin | grep "$TF_VAR_git_ref"   # must print a line; if empty, it isn't on GitHub
```

Keep this terminal open. Every following command needs `TF_VAR_git_ref`. If you open a new
terminal, export it again.

### 2. Pre-flight: check that it builds

A broken build otherwise costs you 15 minutes of waiting on AWS. Check it locally first:

```sh
docker build -t dodgewuh-backend:preflight backend
docker build -t dodgewuh-frontend:preflight frontend
```

Both must finish without errors.

### 3. Prepare DNS (Porkbun)

In Porkbun → `dodgewuh.fit` → DNS, **delete every apex record of type `A`, `AAAA`, `ALIAS`
or `CNAME`**. Porkbun adds a parking `ALIAS` by default. An `AAAA` record breaks HTTPS
certificate issuance, because the VMs have no IPv6. Leave `MX`, `TXT` and other records alone.

### 4. Plan and apply

```sh
terraform -chdir=infra plan -out=dodgewuh.tfplan
```

Check the last line. It must say **`Plan: 22 to add, 0 to change, 0 to destroy.`** If it
says anything else, stop: something is already deployed, so use [Redeploy](#redeploy)
instead.

```sh
terraform -chdir=infra apply dodgewuh.tfplan
```

This takes 1–2 minutes. When it finishes, the VMs have only just started booting.

### 5. Point DNS at the server (do this right away)

```sh
terraform -chdir=infra output -raw coordinator_public_ip
```

In Porkbun, add an **`A` record** with host **empty** (the apex), answer = that IP, TTL
600. Then check it:

```sh
dig +short A dodgewuh.fit @1.1.1.1      # must print the IP
dig +short AAAA dodgewuh.fit @1.1.1.1   # must print nothing
```

Doing this now gives DNS time to propagate while the VMs build. Caddy requests the HTTPS
certificate at the very end of the build.

### 6. Wait for both VMs to finish building (about 15–20 minutes)

You can watch from your laptop, with no shell on the VMs needed:

```sh
terraform -chdir=infra output instance_ids
aws ec2 get-console-output --region us-east-2 --latest --output text \
  --instance-id <worker id> | tail -n 20
aws ec2 get-console-output --region us-east-2 --latest --output text \
  --instance-id <coordinator id> | tail -n 20
```

Repeat every few minutes. Each VM is done when its output contains:

- worker: `dodgewuh worker is up at <sha>`
- coordinator: `dodgewuh coordinator is up at <sha>`

If you see `Failed to run module scripts_user`, or an error and no new output for 10
minutes, go to [When something fails](#when-something-fails).

### 7. Verify

```sh
curl -fsS https://dodgewuh.fit/api/health
# {"status":"ok","build":"<sha>","rooms":0}
git rev-parse --short=12 "$TF_VAR_git_ref"   # must equal "build" above
```

Then do the real check: open `https://dodgewuh.fit` on a laptop and create a room. Join it
from a phone and play a round. If a match starts, the coordinator, worker, database,
WebSockets and HTTPS all work.

**Done.** Back up `infra/terraform.tfstate` (see [Terraform state](#terraform-state)).

---

## Redeploy

Use this to ship a newer commit, or to apply changes to `infra/` or `deploy/`.

> ⚠️ A redeploy **replaces both VMs**. The site is **down for about 20 minutes** and any
> match in progress is lost. Don't redeploy during judging or a demo.
>
> Kept: the IP address (no DNS change), match history in Postgres, and the HTTPS certificate.

### 1. Push the new commit

```sh
git status                    # must be clean
git push origin main
export TF_VAR_git_ref=$(git rev-parse HEAD)
git ls-remote origin | grep "$TF_VAR_git_ref"   # must print a line
```

### 2. Pre-flight builds

```sh
docker build -t dodgewuh-backend:preflight backend
docker build -t dodgewuh-frontend:preflight frontend
```

### 3. Snapshot the database disk (the backup)

```sh
aws ec2 create-snapshot --region us-east-2 \
  --volume-id "$(terraform -chdir=infra output -raw postgres_volume_id)" \
  --description "dodgewuh before $TF_VAR_git_ref"
```

The snapshot is stored separately from Terraform, so it survives even a `destroy`.
Delete old snapshots in the EC2 console → Snapshots when you no longer need them.

### 4. Plan, and read it before applying

```sh
terraform -chdir=infra plan -out=dodgewuh.tfplan
```

It must say **`Plan: 4 to add, 0 to change, 4 to destroy.`** The four replaced resources must be:

- `aws_instance.worker`
- `aws_instance.coordinator`
- `aws_eip_association.coordinator`
- `aws_volume_attachment.postgres`

**If the plan destroys `aws_ebs_volume.postgres` or `aws_eip.coordinator`, stop.** The
first deletes the database and the second changes the IP. Don't apply until you know why.

If it says `No changes`, `git_ref` is the same as what's already deployed.

### 5. Apply

```sh
terraform -chdir=infra apply dodgewuh.tfplan
```

This takes 3–5 minutes. Terraform shuts the old coordinator down cleanly, so Postgres stops
safely, then moves the database disk to the new VM.

### 6. Wait and verify

Same as fresh deploy [step 6](#6-wait-for-both-vms-to-finish-building-about-1520-minutes)
and [step 7](#7-verify). The instance IDs are new, so run `output instance_ids` again. No
DNS change is needed.

### Rolling back

Run the redeploy steps with the previous commit:
`export TF_VAR_git_ref=<previous full SHA>`.

One caveat: if the newer commit added a database migration (a new file in
`backend/migrations/versions/`), the database has already been upgraded and the older code
may not work with it. In that case, roll forward with a fix instead. As a last resort,
restore the snapshot from step 3 (see [Restoring a snapshot](#restoring-a-snapshot)).

---

## When something fails

Open a shell on the VM:

```sh
terraform -chdir=infra output session_commands   # copy the coordinator or worker command, then run it
sudo -i
cloud-init status --long                          # "status: done" means success
tail -n 80 /var/log/cloud-init-output.log         # the failing step is near the bottom
cd /opt/dodgewuh/src/deploy
docker compose ps
docker compose logs --tail 100 <service>          # coordinator | postgres | caddy | game-worker
```

| Symptom | Cause and fix |
| --- | --- |
| Build step failed (`npm`, `uv`, `docker build`) | That commit doesn't build. Fix it, push, and [redeploy](#redeploy). Run the pre-flight builds next time. |
| `fatal: couldn't find remote ref` | The commit wasn't pushed, or the repo isn't public. Push, then redeploy. |
| `PostgreSQL volume did not attach` | Rare AWS delay. Redeploy with the same `git_ref` by running `terraform -chdir=infra apply -replace=aws_instance.coordinator`. |
| `curl` fails with a TLS or certificate error | DNS is wrong or still propagating. Re-run the `dig` checks from step 5, then `docker compose logs caddy`. Caddy keeps retrying, so the site works within minutes of DNS being correct. |
| `/api/health` returns 503 | Database problem: `docker compose logs postgres coordinator`. |
| Rooms are created but a match never starts | Worker problem. Check `docker compose logs game-worker` on the worker and `docker compose logs coordinator` on the coordinator. |
| Phone can't join (connection closes immediately) | The page must be opened at exactly `https://dodgewuh.fit`. `www.` or `http://` won't work. |
| `RATE_LIMIT` when many people join at once | There's a limit of 30 joins/min per IP, and a venue's Wi-Fi is one IP. Wait a moment and retry. |
| `"build"` doesn't match your commit | `TF_VAR_git_ref` wasn't what you thought. Check `git -C /opt/dodgewuh/src log -1`. |

After fixing something by hand on a VM, run `docker compose up -d --wait` from
`/opt/dodgewuh/src/deploy` (as root). Hand edits are lost at the next redeploy; put the real
fix in the repo.

---

## Settings

You only need `git_ref`. Override the others with `export TF_VAR_<name>=…` or in
`infra/terraform.tfvars` (gitignored; see `terraform.tfvars.example`).

| Variable | Default | |
| --- | --- | --- |
| `git_ref` | required | Full 40-character SHA of a pushed commit. Changing it means a redeploy. |
| `domain` | `dodgewuh.fit` | Bare hostname, no `https://`. If you change it, also change the DNS record. |
| `instance_type` | `t3.small` | Both VMs. Don't go below 2 GiB RAM, or the frontend build may fail. |
| `cpu_credits` | `unlimited` | `standard` caps cost but throttles the VMs to 20% CPU under sustained load. |

---

## Terraform state

Terraform records what it created in `infra/terraform.tfstate`, **on the laptop that ran
`apply`**. It isn't in git and must never be committed: it contains the worker secret.

- **Always deploy from that same laptop.** Running `apply` from another machine with no state
  file creates a second, duplicate deployment.
- **Back it up** after every apply to a private location such as a password manager or a
  private drive.
- If it's lost, Terraform can no longer manage or destroy the deployment, and you'd have to
  delete everything by hand in the AWS console.

---

## Teardown

```sh
terraform -chdir=infra destroy            # review, then type: yes
```

This deletes both VMs, the network, the database disk and the IP. Then delete the `A`
record in Porkbun. If you took snapshots during redeploys, delete them in the EC2 console →
Snapshots. Terraform doesn't manage them, so they keep costing money until you do.

## Restoring a snapshot

Only needed after data loss.

1. EC2 console → Snapshots → select it → **Create volume from snapshot**. Use gp3,
   encrypted, in the **same Availability Zone** as the current `dodgewuh-postgres` volume.
2. Tell Terraform to use the new volume in place of the old one:
   ```sh
   terraform -chdir=infra state rm aws_volume_attachment.postgres aws_ebs_volume.postgres
   terraform -chdir=infra import aws_ebs_volume.postgres <new volume id>
   terraform -chdir=infra apply -replace=aws_instance.coordinator
   ```
3. Delete the old volume in the console once the site works.

## Cost

While it's running: two t3.small VMs, about 40 GiB of gp3 disk, two public IPv4 addresses,
and CPU above the baseline when `cpu_credits = unlimited`. Run `terraform destroy` when the
event is over.
