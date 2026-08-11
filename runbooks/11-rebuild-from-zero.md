# Runbook 11 · Rebuild the lab from zero

**Goal** The order of operations to bring everything back after total loss.

**Time** A weekend, realistically.
**Prerequisites** The backup archives, this repository, and the credentials in
Vaultwarden — which means an export of Vaultwarden that is not stored only
inside Vaultwarden.

---

## Read this first

**The dependency that breaks everything: Vaultwarden holds the credentials
needed to rebuild Vaultwarden.**

The Cloudflare API token, the Proxmox root password, the tunnel token, the
database passwords. If the only copy is in the vault and the vault is gone, no
amount of documentation helps.

**Keep an encrypted Vaultwarden export somewhere outside this lab.** A file on a
USB stick in a drawer, an encrypted archive in a cloud account. Anywhere that is
not the machine you are rebuilding. This is the single most important line in
this runbook.

---

## Order of operations

The order is not arbitrary. Each layer depends on the one before it.

```
1. network        router, switch, addressing
2. DNS            AdGuard on the Pi           <- nothing resolves until this
3. ingress        NPM + certificate           <- no friendly names until this
4. hypervisor     Proxmox on P1
5. cluster        P2, P3, quorum
6. Docker host    LXC 102
7. secrets        Vaultwarden FIRST           <- everything else needs it
8. observability  Prometheus, Grafana, Glance
9. services       everything else
10. verify        the checklist at the bottom
```

Rebuilding services before DNS means every step fails for reasons that have
nothing to do with the step.

---

## 1 · Network

FRITZ!Box: `192.168.178.1`, DHCP on, DNS pointing at `192.168.178.178` once the
Pi exists. Switch is unmanaged; plug it in.

Addressing plan:
[`inventory/inventory.yml`](../inventory/inventory.yml).

---

## 2 · DNS

DietPi on the Pi, Docker, AdGuard Home.
→ [Runbook 03](03-adguard-home-dns.md)

**Nothing on the network resolves a name until this is running.** Do it second
for a reason.

---

## 3 · Ingress and certificates

Nginx Proxy Manager on the Pi, wildcard certificate over DNS-01.
→ [Runbook 04](04-nginx-proxy-manager-vhost.md)

Needs the Cloudflare API token. If it is not available, issue a new one from the
Cloudflare dashboard — which needs access to the Cloudflare account, which needs
a password, which is in the vault. See the warning at the top.

---

## 4 · Proxmox on P1

Install Proxmox VE. Static `192.168.178.20`. Then:

```bash
# switch off the enterprise repository, or apt update fails forever
sed -i 's/^deb/#deb/' /etc/apt/sources.list.d/pve-enterprise.list
echo "deb http://download.proxmox.com/debian/pve $(. /etc/os-release && echo "$VERSION_CODENAME") pve-no-subscription" \
  > /etc/apt/sources.list.d/pve-no-subscription.list
apt update && apt full-upgrade -y

pveam update
pveam download local debian-12-standard_12.7-1_amd64.tar.zst
apt install -y prometheus-node-exporter
```

Restore the guests, if archives survived:

```bash
pct restore 102 /path/to/vzdump-lxc-102-*.tar.zst --storage local-lvm --start 0
```

If they did not, rebuild from the runbooks. That is what they are for.

---

## 5 · Cluster

P2 and P3, then join them.
→ [Runbook 08](08-add-a-node-to-the-cluster.md)

Not urgent. A single node runs everything; the cluster adds quorum and
maintenance headroom. Do it once services are back.

---

## 6 · Docker host

LXC 102 with `nesting=1,keyctl=1`, Docker installed.
→ [Runbook 01](01-create-an-lxc-container.md),
[Runbook 02](02-portainer-on-a-new-lxc.md)

---

## 7 · Vaultwarden, first of the services

Because every subsequent step needs a password out of it.

```bash
mkdir -p /opt/vaultwarden && cd /opt/vaultwarden
# compose/vaultwarden/docker-compose.example.yml
docker compose up -d
```

Restore the data volume from backup:

```bash
docker compose down
docker run --rm -v vaultwarden_data:/data -v /srv/backup:/b \
  alpine sh -c "cd /data && tar xzf /b/vaultwarden-2026-08-11.tar.gz"
docker compose up -d
```

Then log in and **verify you can read an actual password** before continuing.

---

## 8 · Observability

Glance first — it is five minutes and it gives you a checklist that updates
itself as you bring services back.
→ [Runbook 05](05-glance-dashboard.md), [Runbook 10](10-monitoring-stack.md)

---

## 9 · Everything else

In whatever order matters to whoever is waiting for it. Each service:

1. create the LXC, if it needs its own → [Runbook 01](01-create-an-lxc-container.md)
2. install Docker → [Runbook 02](02-portainer-on-a-new-lxc.md)
3. copy the compose file from [`compose/`](../compose/), fill in `.env`
4. restore its data volume from backup
5. add the proxy host → [Runbook 04](04-nginx-proxy-manager-vhost.md)
6. add it to Glance and to `health-check.sh`

---

## 10 · Verify

```bash
./scripts/health-check.sh
```

Then by hand:

- [ ] every device on the LAN resolves names
- [ ] `https://` on an internal service, no certificate warning
- [ ] the public hostname answers **from mobile data**, not wifi
- [ ] Vaultwarden opens and shows real entries
- [ ] `pvecm status` says Quorate on all three nodes
- [ ] Prometheus `/targets` all UP
- [ ] a backup job runs and produces an archive
- [ ] **restore one guest** → [Runbook 09](09-backup-restore-drill.md)

The last one is not optional. Rebuilding the lab without confirming that its
backups work leaves you exactly where you started.

---

## What this reveals

Running through this list, even on paper, exposes the real dependencies:

- **DNS is load-bearing for everything.** One container on one Raspberry Pi.
- **Vaultwarden is circular.** It holds what is needed to rebuild it.
- **The Cloudflare account is a hard external dependency.** Lose access to it
  and every certificate and the public hostname go with it.
- **Documentation is a backup.** The services whose rebuild is written down do
  not need an image backup; they need their data backed up and their recipe
  written down. That is the argument for this whole repository, and this runbook
  is where it gets tested.
