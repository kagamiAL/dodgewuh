#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl file e2fsprogs
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
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
install -d -m 0755 /etc/docker /opt/dodgewuh
cat > /etc/docker/daemon.json <<'EOF'
{"log-driver":"local","log-opts":{"max-size":"10m","max-file":"3"}}
EOF
if ! snap list amazon-ssm-agent >/dev/null 2>&1; then
  snap install amazon-ssm-agent --classic
fi
snap start --enable amazon-ssm-agent
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
