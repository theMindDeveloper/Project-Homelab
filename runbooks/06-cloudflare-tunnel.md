# Runbook 06 · Publish one service with a Cloudflare Tunnel

**Goal** `apache.theminddev.com` reachable from the internet, with **no inbound
firewall rule and no port forward**.

**Time** 15 minutes.
**Prerequisites** A domain on Cloudflare. Docker on LXC 102.
**Reverses cleanly?** Yes — delete the tunnel.

---

## How it works

```
internet --> Cloudflare edge
                  |
                  |  down an EXISTING outbound connection
                  v
            cloudflared (LXC 102)  --> Apache :80
```

`cloudflared` dials **out** to Cloudflare and holds the connection open.
Requests for the published hostname come back down that connection. Nothing
listens for inbound traffic, so there is nothing to forward and nothing to
firewall.

**What this gives you**

- no inbound firewall rule, no port forward
- the origin's public IP is never in DNS
- DDoS absorbed at Cloudflare's edge
- works behind CGNAT, where port forwarding is impossible

**What it costs, stated plainly**

- **Cloudflare terminates TLS at their edge and can read the plaintext.** The
  tunnel is not end-to-end encrypted to the origin. For a static site that is
  fine. For anything sensitive it would not be, and saying "it goes through a
  tunnel so it is encrypted" would be wrong.
- a dependency on a third party for availability
- Cloudflare's free plan does not permit proxying arbitrary non-HTML content

---

## 1 · Create the tunnel

Cloudflare **Zero Trust → Networks → Tunnels → Create a tunnel**

1. Type: **Cloudflared**
2. Name it after the machine it runs on, not the service.
3. Choose **Docker** on the connector screen and copy the token.

**The token is a credential.** It authenticates this connector as the tunnel;
anyone holding it can serve traffic as that hostname. It cannot be rotated — if
it leaks, delete the tunnel and create a new one.

---

## 2 · Run the connector

```bash
mkdir -p /opt/cloudflared && cd /opt/cloudflared
cp /path/to/compose/cloudflared/docker-compose.example.yml docker-compose.yml
cp /path/to/compose/cloudflared/.env.example .env
$EDITOR .env                 # paste the token
chmod 600 .env
docker compose up -d
docker compose logs -f
```

Expect `Registered tunnel connection` four times, once per Cloudflare edge
location. The dashboard should show the connector as **Healthy**.

Note there is no `ports:` section in that compose file. **Nothing listens.**
That is the entire security argument in one absence.

---

## 3 · Route the hostname

In the tunnel's **Public Hostname** tab:

| Field | Value |
|---|---|
| Subdomain | `apache` |
| Domain | `theminddev.com` |
| Service Type | HTTP |
| URL | `apache:80` or `192.168.178.87:80` |

Cloudflare creates the `CNAME` automatically, pointing at
`<tunnel-id>.cfargotunnel.com`. **Do not create it by hand**, and do not leave a
stale `A` record for the same name — an `A` record with a real address defeats
the entire purpose by publishing the origin.

Use the Docker service name (`apache:80`) if both containers share a network. It
survives an address change.

---

## 4 · Verify

```bash
dig +short apache.theminddev.com          # a Cloudflare address, NOT yours
curl -I https://apache.theminddev.com

# from OUTSIDE the network - mobile data, not wifi
curl -I https://apache.theminddev.com
```

The first check is the important one. If `dig` returns your public IP, something
is wrong: either a leftover `A` record, or the hostname is not going through the
tunnel at all.

Test from mobile data. Testing from inside the LAN proves nothing about whether
the internet can reach it.

---

## 5 · Harden the origin

This container is the only thing the internet can reach. Treat it accordingly:
read-only root filesystem, all capabilities dropped, static content only, no
database behind it. See
[`compose/apache/docker-compose.example.yml`](../compose/apache/docker-compose.example.yml).

For anything that is not deliberately public, add **Cloudflare Access** in front
of the hostname. It puts an identity check at the edge, before a request ever
enters the tunnel, and it is free for small numbers of users.

---

## If it goes wrong

| Symptom | Cause |
|---|---|
| **Error 1033** | the connector is not connected — `docker compose logs` |
| **502 Bad Gateway** | the connector is up, the origin URL is wrong or the service is down |
| **DNS returns your public IP** | a leftover `A` record — delete it |
| **works on LAN, not outside** | you are testing on wifi; use mobile data |
| **certificate warning** | the hostname is not in the tunnel's public hostname list |

---

## Undo

```bash
docker compose down
```

Delete the tunnel in the Cloudflare dashboard. The `CNAME` goes with it.
