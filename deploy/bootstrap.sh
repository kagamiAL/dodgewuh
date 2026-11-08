#!/usr/bin/env bash
# EC2 user data body. Terraform prepends exports for:
#   DODGEWUH_ROLE (coordinator|worker), DODGEWUH_REPO, DODGEWUH_REF, GAME_WORKER_SECRET,
#   and on the coordinator DODGEWUH_DATA_VOLUME_ID, DOMAIN, GAME_WORKER_URL.
# Runs once per instance: installs Docker, clones the repo at DODGEWUH_REF, builds and starts the stack.
# Progress/failures: /var/log/cloud-init-output.log (or `cloud-init status --long`).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
: "${DODGEWUH_ROLE:?}" "${DODGEWUH_REPO:?}" "${DODGEWUH_REF:?}" "${GAME_WORKER_SECRET:?}"
apt_get() { apt-get -o DPkg::Lock::Timeout=600 "$@"; }

apt_get update
apt_get install -y ca-certificates curl file e2fsprogs git openssl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL --retry 5 https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt_get update
apt_get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
install -d -m 0755 /etc/docker /opt/dodgewuh
cat > /etc/docker/daemon.json <<'EOF'
{"log-driver":"local","log-opts":{"max-size":"10m","max-file":"3"}}
EOF
if ! snap list amazon-ssm-agent >/dev/null 2>&1; then
  snap install amazon-ssm-agent --classic
fi
snap start --enable amazon-ssm-agent

# t3.small has 2 GiB RAM; swap keeps the image builds (npm ci + vite) from being OOM-killed.
if [[ ! -f /swapfile ]]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi
swapon --show | grep -q /swapfile || swapon /swapfile

# Terraform attaches the data volume after instance creation. Never use a guessed
# /dev/nvme number: match the EBS volume ID before formatting or mounting.
if [[ -n "${DODGEWUH_DATA_VOLUME_ID:-}" ]]; then
  data_disk="/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_${DODGEWUH_DATA_VOLUME_ID//-/}"
  for attempt in $(seq 1 120); do
    [[ -b "$data_disk" ]] && break
    sleep 5
  done
  [[ -b "$data_disk" ]] || { echo "PostgreSQL volume did not attach" >&2; exit 1; }
  disk_type=$(blkid -s TYPE -o value "$data_disk" || true)
  if [[ -z "$disk_type" ]]; then
    [[ "$(file -bsL "$data_disk")" == "data" ]] || { echo "Unrecognized data disk; refusing to format" >&2; exit 1; }
    mkfs.ext4 "$data_disk"
  elif [[ "$disk_type" != "ext4" ]]; then
    echo "Unexpected filesystem $disk_type; refusing to modify" >&2
    exit 1
  fi
  disk_uuid=$(blkid -s UUID -o value "$data_disk")
  install -d -m 0755 /opt/dodgewuh/data
  if ! grep -q "UUID=$disk_uuid " /etc/fstab; then
    echo "UUID=$disk_uuid /opt/dodgewuh/data ext4 defaults,nofail 0 2" >> /etc/fstab
  fi
  mountpoint -q /opt/dodgewuh/data || mount /opt/dodgewuh/data
  # Preserve PostgreSQL's ownership and permissions on an existing data directory.
  if [[ ! -d /opt/dodgewuh/data/postgres ]]; then
    install -d -m 0700 /opt/dodgewuh/data/postgres
  fi
  install -d -m 0700 /opt/dodgewuh/data/caddy
  install -d -m 0755 /etc/systemd/system/docker.service.d
  cat > /etc/systemd/system/docker.service.d/data-volume.conf <<'EOF'
[Unit]
RequiresMountsFor=/opt/dodgewuh/data
EOF
  systemctl daemon-reload
fi

systemctl enable docker
systemctl restart docker
docker version
docker compose version

# ---- Application -------------------------------------------------------------
src=/opt/dodgewuh/src
if [[ ! -d "$src/.git" ]]; then
  git init -q "$src"
  git -C "$src" remote add origin "$DODGEWUH_REPO"
fi
# Fetching by SHA works on GitHub; branch and tag names work too.
git -C "$src" fetch --depth 1 origin "$DODGEWUH_REF"
git -C "$src" checkout -q --force FETCH_HEAD
build_sha=$(git -C "$src" rev-parse --short=12 HEAD)
cd "$src/deploy"

if [[ "$DODGEWUH_ROLE" == worker ]]; then
  imds_token=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
  private_ip=$(curl -fsS -H "X-aws-ec2-metadata-token: $imds_token" http://169.254.169.254/latest/meta-data/local-ipv4)
  umask 077
  cat > .env <<EOF
COMPOSE_FILE=compose.worker.yaml
BUILD_SHA=$build_sha
GAME_WORKER_SECRET=$GAME_WORKER_SECRET
WORKER_PRIVATE_IP=$private_ip
EOF
  umask 022
  docker compose build
  docker compose up -d --wait
elif [[ "$DODGEWUH_ROLE" == coordinator ]]; then
  : "${DOMAIN:?}" "${GAME_WORKER_URL:?}"
  # Generated on the host; never leaves it. Stored on the data volume, not the root disk:
  # Postgres only reads it when initialising an empty data directory, so it must survive VM
  # replacement together with the data. Compose bind-mounts the file into both containers and
  # the coordinator runs as a non-root user, so the file is 0444 inside a root-only 0700 dir.
  install -d -m 0700 /opt/dodgewuh/data/secrets
  password_file=/opt/dodgewuh/data/secrets/postgres_password
  if [[ ! -s "$password_file" ]]; then
    (umask 077; openssl rand -hex 32 > "$password_file")
  fi
  chmod 0444 "$password_file"
  umask 077
  cat > .env <<EOF
COMPOSE_FILE=compose.coordinator.yaml
BUILD_SHA=$build_sha
GAME_WORKER_SECRET=$GAME_WORKER_SECRET
DOMAIN=$DOMAIN
GAME_WORKER_URL=$GAME_WORKER_URL
POSTGRES_PASSWORD_FILE=$password_file
EOF
  umask 022
  docker compose build
  # The coordinator queries its tables on startup, so migrate before starting it.
  docker compose up -d --wait postgres
  docker compose run --rm --no-deps coordinator /app/.venv/bin/alembic upgrade head
  docker compose up -d --wait
else
  echo "Unknown DODGEWUH_ROLE=$DODGEWUH_ROLE" >&2
  exit 1
fi
echo "dodgewuh $DODGEWUH_ROLE is up at $build_sha"
