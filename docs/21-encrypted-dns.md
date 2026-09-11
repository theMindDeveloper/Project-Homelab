# Encrypted DNS (DoH and DoT)

What DNS over HTTPS and DNS over TLS actually encrypt, where the encryption
starts and ends in this lab, and what it still does not hide.

Written after the [September 2026 privacy update](reports/2026-09-11-privacy-update.md).
The setup steps are in [runbook 03](../runbooks/03-adguard-home-dns.md#upstream-resolvers).

---

## The problem

Normal DNS is plain text on port 53. Every lookup ("what is the IP of
example.com?") travels like a postcard. Anyone on the path can read it, log it,
or even change the answer. In practice that means the ISP sees every name every
device in the house looks up.

HTTPS does not help here, because the DNS lookup happens **before** the HTTPS
connection is opened.

---

## DoT and DoH

Both put the same DNS question inside a TLS connection. The difference is only
the "door" they use.

| | DNS over TLS (DoT) | DNS over HTTPS (DoH) |
|---|---|---|
| Port | **853** | **443** |
| Looks like | DNS, just encrypted | normal web traffic |
| Easy to block? | yes, block 853 | hard, you would have to block HTTPS |
| AdGuard syntax | `tls://dns.quad9.net` | `https://dns.quad9.net/dns-query` |

There is also DoQ (DNS over QUIC, `quic://`). Not used here.

---

## The part that confused me: who encrypts?

The path of a lookup in this lab:

```
PC ──plain──> AdGuard (Pi) ══encrypted══> FRITZ!Box ══> ISP ══> Quad9
```

- **AdGuard encrypts**, on the Pi, before the packet leaves.
- **Quad9 decrypts**, at the other end.
- **The FRITZ!Box and the ISP only carry it.** They need the outer header
  (from my public IP, to Quad9, port 443 or 853) to deliver the packet, but the
  content (the name being looked up) is encrypted.

Same idea as opening a bank website: the browser and the bank encrypt between
themselves and every router in between just forwards bytes it cannot read.

### How two machines agree on a key while the ISP watches

The TLS handshake at the start of the connection does two jobs:

1. **Key exchange (Diffie-Hellman).** Both sides send each other public values
   and each combines them with a secret value that never leaves the machine.
   Both end up with the same key. Someone who saw everything on the wire still
   cannot compute it. The usual analogy is mixing paint: easy to mix, not
   possible to un-mix.
2. **Certificate check.** Quad9 shows a certificate for `dns.quad9.net`, signed
   by a CA the Pi already trusts. Someone pretending to be Quad9 cannot show a
   valid one, so AdGuard refuses to talk to them.

That second point is why a wrong system clock breaks encrypted DNS: certificates
have validity dates.

### The two legs

| Leg | From → to | Encrypted? | Why that is OK |
|---|---|---|---|
| 1 | device → AdGuard | **no**, plain port 53 | never leaves the house LAN |
| 2 | AdGuard → Quad9 | **yes**, DoH or DoT | this is the part the ISP can see |

So "DoH/DoT on AdGuard" in this lab means **encrypted upstream**. AdGuard can
also *serve* DoH/DoT to clients (it needs a certificate for that), but that is
not set up and would mostly matter for devices outside the house.

---

## What it hides, and what it does not

| Hidden from the ISP | Still visible to the ISP |
|---|---|
| which names are looked up | the IP addresses connected to right after the lookup |
| the DNS answers | that I use Quad9, when, and how much |
| | the hostname in the TLS handshake of later HTTPS connections (**SNI**) |
| | anything sent over plain `http://` |

And Quad9 itself sees every query, together with my public IP. Encrypted DNS
moves trust from the ISP to the resolver, it does not remove it.

The gap between "hides the name" and "hides the connection" is what a VPN
closes. See [VPNs and kill switches](22-vpns-and-kill-switches.md).

---

## Why Quad9

- Non-profit, based in Switzerland, blocks known malware domains on its side.
- Supports both DoH and DoT on the same hostname.
- A lot of guides recommend Mullvad's public DNS (`dns.mullvad.net`). Mullvad
  announced in September 2026 that its **public encrypted DNS shuts down on
  2 November 2026** and it sponsors Quad9 instead. So there was no point
  building on that.

---

## The AdGuard settings that matter

Settings → DNS settings:

```text
https://dns.quad9.net/dns-query
tls://dns.quad9.net
[/fritz.box/]192.168.178.1
```

| Setting | Value | Why |
|---|---|---|
| Upstream line 1 | DoH | encrypted |
| Upstream line 2 | DoT | encrypted backup, AdGuard picks the faster one |
| `[/fritz.box/]192.168.178.1` | **conditional upstream** | names ending in `fritz.box` go to the router, because Quad9 does not know my house. Without it those names break and leak to the internet. |
| Bootstrap DNS | `9.9.9.9`, `149.112.112.112` | to reach `dns.quad9.net`, AdGuard first needs its IP. This one plain lookup is safe because the certificate check happens afterwards. |
| Private reverse DNS | `192.168.178.1` | the query log shows device names instead of IPs |
| DNSSEC | on | checks that answers are signed and not forged |

**Ad blocking is not affected.** AdGuard checks its blocklists first. A blocked
name is answered locally and never reaches Quad9 at all. Only allowed names go
upstream.

**Port forwards are not involved either.** AdGuard opens the connection to
Quad9 (outbound) and the answer comes back on that same connection. Port
forwards are only for connections that start outside.

---

## How to check it is working

A DNS leak test and a packet capture answer different questions.

| Check | Answers | Does not answer |
|---|---|---|
| dnsleaktest.com (extended) | **who** resolves my queries (should be Quad9 only, no ISP servers) | whether it is encrypted |
| AdGuard dashboard → Top upstreams, or a Query log entry | **which upstream** answered (`https://...` = DoH, `tls://...` = DoT) | what actually left the Pi |
| `tcpdump` on the Pi | **what actually leaves**, and on which port | nothing, this is the real proof |

```bash
# plain DNS leaving the house: should stay (almost) empty while browsing
sudo tcpdump -ni any 'port 53 and not net 192.168.178.0/24'

# encrypted DNS to Quad9: should show traffic on .443 and/or .853
sudo tcpdump -ni any 'host 9.9.9.9 or host 149.112.112.112'
```

Port numbers tell the story: **53 = plain, 853 = DoT, 443 = DoH.** An
occasional port-53 packet to `9.9.9.9` is the bootstrap lookup refreshing the
IP of `dns.quad9.net`.

A nice extra test: `dig @9.9.9.9 example.com` while capturing port 53 with
`tcpdump -A` shows the name in readable text. The same name asked through
AdGuard never shows up readable on 443/853.

---

## Gotchas

**Browser "Secure DNS" bypasses AdGuard.** Chrome, Edge and Firefox can send
DoH straight to Google or Cloudflare. No blocking, no query log entry. Turn it
off or set it to "use current provider". A leak test showing Google or
Cloudflare resolvers is the symptom.

**IPv6 can sneak around AdGuard.** The FRITZ!Box can announce *itself* as the
IPv6 DNS server, so devices ask the router instead of AdGuard. Symptom: a device
never appears in the query log.

**Windows can do DoH itself.** Same problem as the browser, it would skip
AdGuard. Leave it off on LAN devices.

**"Could not be used" in Test upstreams** is a generic message. See
[troubleshooting](10-troubleshooting.md#adguard-says-an-upstream-could-not-be-used).

---

## Key points

1. AdGuard is the DNS server. DoH/DoT here means encrypting the **upstream leg**.
2. Encryption is between the two ends that have the keys (AdGuard and Quad9).
   Everything in between just delivers sealed packets.
3. Encrypted DNS hides the **name**, not the **connection**. That is a VPN's job.

---

**Next:** [VPNs and kill switches](22-vpns-and-kill-switches.md) ·
**Back to:** [wiki index](README.md)
