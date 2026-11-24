# Computer Networks Project — Private Network Service Platform

A two-phase, team-based local networking project that builds and observes a private service environment using macOS laptops connected to the same local network.

> **Core principle:** The application stays simple; the network is the project.

## Overview

This project demonstrates how a client request travels through a real network stack:

```text
Client
  ↓
Private DNS
  ↓
TCP
  ↓
TLS / HTTPS
  ↓
nginx Reverse Proxy / Load Balancer
  ↓
Backend A or Backend B
  ↓
nginx
  ↓
Client
```

The project services run locally. No cloud hosting is required; external DNS forwarding is optional.

### Phase 1 focuses on

- Private DNS using `dnsmasq`
- Simple HTTP/REST backend services
- nginx reverse proxy
- Round-robin load balancing
- HTTPS and TLS termination
- DNS, TCP, TLS, and HTTP packet analysis with Wireshark
- HTTP caching using `Cache-Control` and conditional requests

### Phase 2 focuses on

- Backup DNS
- DNS TTL and controlled record changes
- Backend service isolation
- Backend health/failover
- DNS-based edge migration
- Troubleshooting injected failures

---

# Architecture

## Two-Mac Implementation

Our implementation uses two physical Macs and combines multiple logical roles.

| Machine | Roles | Services |
|---|---|---|
| Mac 1 (Khushi) | Primary DNS, Backend A, Client, standby edge | `dnsmasq :53`, Backend A `:3001` |
| Mac 2 (Satvik) | nginx Edge, Backend B, Client, backup DNS | nginx `:443` / `:8443`, Backend B `:3002` |

### Network topology

```text
                    PRIVATE WI-FI / LAN
                         Same Network
                              |
                +-------------+-------------+
                |                           |
                v                           v
        +---------------+           +---------------+
        |     Mac 1     |           |     Mac 2     |
        |  10.7.8.224   |           |  10.7.15.7   |
        |---------------|           |---------------|
        | Primary DNS   |           | nginx Edge    |
        | dnsmasq :53   |           | HTTPS :443    |
        |               |           | / :8443       |
        | Backend A     |           | TLS Termination|
        | HTTP :3001    |           | Load Balancer |
        |               |           |               |
        | Client        |           | Backend B     |
        |               |           | HTTP :3002    |
        +---------------+           | Client        |
                                    +---------------+
```

### Private service domain

```text
app.dotenv.test  →  10.7.15.7
api.dotenv.test  →  10.7.15.7 (optional alias; HTTPS requires matching certificate)
```

The client connects to the nginx edge by domain name. It does not connect directly to either backend.

---


---

# Network Configuration

Record the actual values used by your team:

```text
Mac 1 IP = 10.7.8.224
Mac 2 IP =10.7.15.7

Primary DNS = 10.7.8.224:53
nginx Edge  = 10.7.15.7:443 or :8443

Backend A = 10.7.8.224:3001
Backend B = 10.7.15.7:3002
```

Find the current IP address:

```bash
ipconfig getifaddr en0
```

Inspect the interface:

```bash
ifconfig en0
```

Verify connectivity:

### Mac 1

```bash
ping -c 4 10.7.15.7
```

### Mac 2

```bash
ping -c 4 10.7.8.224
```

---

# Private DNS — dnsmasq

Mac 1 runs the primary private DNS service.

Example configuration:

```conf
port=53
listen-address=10.7.8.224
local-ttl=30

no-resolv

server=1.1.1.1
server=8.8.8.8

address=/app.dotenv.test/10.7.15.7
address=/api.dotenv.test/10.7.15.7

no-hosts

cache-size=1000
log-queries
```

## Test the configuration

```bash
dnsmasq --test --conf-file="$(brew --prefix)/etc/dnsmasq.conf"
```

## Start dnsmasq

```bash
sudo brew services start dnsmasq
```

## Test the project DNS record

```bash
dig @10.7.8.224 app.dotenv.test
```

or:

```bash
nslookup app.dotenv.test 10.7.8.224
```

Expected result:

```text
app.dotenv.test → 10.7.15.7
```

The final application should be accessed using the domain name, not a direct IP address.

---

# Backend A

Backend A runs on Mac 1 using port `3001`.

Required endpoints:

```text
GET /
GET /api/status
```

Example status response:

```json
{
  "backend": "A",
  "status": "ok"
}
```

Response header:

```http
X-Backend: A
```

The backend should listen on a LAN-accessible interface.

Test locally:

```bash
curl -i http://127.0.0.1:3001/api/status
```

Test across the LAN:

```bash
curl -i http://<MAC1_IP>:3001/api/status
```

---

# Backend B

Backend B runs on Mac 2 using port `3002`.

Example response:

```json
{
  "backend": "B",
  "status": "ok"
}
```

Response header:

```http
X-Backend: B
```

Test locally:

```bash
curl -i http://127.0.0.1:3002/api/status
```

Test across the LAN:

```bash
curl -i http://<MAC2_IP>:3002/api/status
```

---

# nginx Reverse Proxy and Load Balancer

Mac 2 runs nginx as the single public entry point.

Example upstream configuration:

```nginx
upstream backends {
    server 10.7.8.224:3001 max_fails=1 fail_timeout=5s;
    server 10.7.15.7:3002 max_fails=1 fail_timeout=5s;
}
```

Example HTTPS server:

```nginx
server {
    listen 443 ssl;
    server_name app.dotenv.test;

    ssl_certificate     /path/to/app.dotenv.test.pem;
    ssl_certificate_key /path/to/app.dotenv.test-key.pem;

    location / {
        proxy_pass http://backends;
        proxy_connect_timeout 2s;
        proxy_read_timeout 5s;
        proxy_next_upstream error timeout http_502 http_503 http_504;
        proxy_next_upstream_tries 2;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

If ports `443`/`80` are unavailable, use `8443`/`8080`.

## Validate nginx

```bash
sudo nginx -t -c "$(brew --prefix)/etc/nginx/nginx.conf"
```

## Start nginx

```bash
sudo nginx -c "$(brew --prefix)/etc/nginx/nginx.conf"
```

## Reload nginx

```bash
sudo nginx -s reload
```

---

# Load Balancing Test

Run repeated requests through the domain:

```bash
for i in {1..10}; do
    curl -si https://app.dotenv.test/api/status | grep -Ei "HTTP/|X-Backend"
done
```

Expected pattern:

```text
HTTP/1.1 200 OK
X-Backend: A

HTTP/1.1 200 OK
X-Backend: B

HTTP/1.1 200 OK
X-Backend: A

HTTP/1.1 200 OK
X-Backend: B
```

The `X-Backend` header is used as application-level evidence of which backend processed each request.

---

# HTTPS / TLS

TLS is terminated at nginx:

```text
Client
  │
  │ HTTPS / TLS
  ▼
nginx
  │
  │ HTTP
  ▼
Backend A / Backend B
```

Create a certificate for:

```text
app.dotenv.test
```

using OpenSSL or a local CA such as `mkcert`.

Install the local CA on client Macs.

Test without bypassing certificate validation:

```bash
curl -v https://app.dotenv.test/api/status
```

Do not use:

```bash
curl -k
```

for the final demonstration.

---

# HTTP Caching

At least one endpoint should return a cache header such as:

```http
Cache-Control: max-age=60
```

An optional ETag can be used:

```http
ETag: "abc123"
```

Inspect headers:

```bash
curl -sD - -o /dev/null https://app.dotenv.test/
```

Conditional request example:

```bash
curl -i \
  -H 'If-None-Match: "abc123"' \
  https://app.dotenv.test/
```

Expected conditional response when the selected backend has the matching ETag (different backend bodies can have different ETags):

```text
HTTP/1.1 304 Not Modified
```

Be prepared to explain:

- Fresh cache hit
- Conditional request
- Full new request

---

# Wireshark Evidence

Capture traffic on the active client interface while making a fresh request.

Example filter:

```text
dns || tcp.port == 443 || tls
```

For port `8443`, adjust the filter accordingly.

## DNS evidence

Show:

```text
Client → DNS Server
Query: app.dotenv.test

DNS Server → Client
Answer: 10.7.15.7
```

## TCP evidence

Show:

```text
SYN
SYN-ACK
ACK
```

Record:

- Client ephemeral source port
- Server destination port
- TCP sequence numbers
- TCP acknowledgement numbers

## TLS evidence

Show:

```text
ClientHello
ServerHello
Certificate / Finished (visibility depends on TLS version)
```

Explain that the application data following the TLS handshake is encrypted.

## HTTP evidence

Run:

```bash
curl -v https://app.dotenv.test/api/status
```

Use the output to show request and response headers.

---

# Complete Request Flow

For one request:

```text
1. Client enters:
   https://app.dotenv.test/api/status

2. DNS lookup:
   app.dotenv.test
          ↓
   10.7.15.7

3. TCP connection:
   SYN → SYN-ACK → ACK

4. TLS handshake:
   ClientHello
   ServerHello
   Certificate
   Key Exchange
   Finished

5. HTTPS request reaches nginx.

6. nginx terminates TLS.

7. nginx selects Backend A or Backend B.

8. Backend returns:
   HTTP 200 OK
   X-Backend: A/B

9. nginx returns the response to the client
   through the encrypted HTTPS connection.
```

---


# Troubleshooting

Diagnose failures layer by layer:

```text
DNS
 ↓
TCP
 ↓
TLS
 ↓
HTTP / Application
```

## Check DNS

```bash
dig app.dotenv.test
```

## Check TCP port

```bash
nc -vz 10.7.15.7 443
```

or:

```bash
nc -vz 10.7.15.7 8443
```

## Check TLS

```bash
curl -v https://app.dotenv.test/api/status
```

## Check the backends directly

```bash
curl http://10.7.8.224:3001/api/status
curl http://10.7.15.7:3002/api/status
```

This helps isolate whether the failure is in DNS, TCP, TLS, nginx, or the backend.

---

# Controlled Failure Scenarios


## One backend stopped

Stop Backend A.

Expected:

```text
Requests continue through Backend B
```

provided nginx failure handling is configured.



# Phase 2 Extensions

Phase 2 builds on the same Phase 1 infrastructure.

## Backup DNS

Run dnsmasq on Satvik's Mac with the same records as the primary, but `listen-address=10.7.15.7`. Configure clients to use both resolvers (for example, in `/etc/resolver/dotenv.test`, list `nameserver 10.7.8.224` and `nameserver 10.7.15.7`).

```bash
# On primary only
sudo brew services stop dnsmasq
# On client
dig @10.7.15.7 app.dotenv.test
curl -v https://app.dotenv.test/api/status
# Restore primary
sudo brew services start dnsmasq
```

Use a fresh lookup and capture DNS traffic to prove backup use; a cached response alone is not proof.

## DNS TTL

Use a short TTL such as:

```text
30 seconds
```

Change the DNS record and observe cached answers until the TTL expires.

## Service Isolation

Restrict direct access to backend ports:

```text
3001
3002
```

so that only the authorized edge can reach them over the LAN. Example PF anchor on Khushi's Mac for Backend A:

```pf
pass in quick on en0 inet proto tcp from 10.7.15.7 to 10.7.8.224 port 3001 keep state
block drop in quick on en0 inet proto tcp from any to 10.7.8.224 port 3001
```

Back up `/etc/pf.conf` and any existing anchor before editing. Declare `anchor "cn_backend"` in the filtering section and load it from `/etc/pf.anchors/cn_backend`. Validate before loading. Backend B can bind to loopback on the original edge, but must be reachable from the standby edge during migration.

```bash
sudo pfctl -nf /etc/pf.conf
sudo pfctl -f /etc/pf.conf
sudo pfctl -E
sudo pfctl -a cn_backend -vvsr
```

Retain the enable token and restore the original configuration after testing. With two Macs, nginx and the client on the same Mac share a source IP; source-IP filtering cannot distinguish them. An allow/block/restore demonstration proves enforcement, not simultaneous isolation of a separate client. Update authorized sources before migration.

## Backend Failover

Stop Backend A and confirm that nginx continues serving Backend B.

Restart Backend A and verify that load balancing resumes.

```bash
# On Khushi's Mac: stop Backend A with Ctrl+C in its terminal
lsof -nP -iTCP:3001 -sTCP:LISTEN
# On Satvik's Mac
for i in {1..10}; do
  curl -sS -w ' HTTP %{http_code}\n' https://app.dotenv.test/api/status
done
```

Expect Backend B only with HTTP 200. Restart A using its original Python launch command, wait at least six seconds, and repeat. nginx uses passive failure detection, not active health probes. Stopping both backends should produce an upstream error (typically 502 for refused connections); restore both afterward.

## Edge Migration

Use a standby nginx edge on Khushi's Mac with the same upstreams and a trusted certificate for `app.dotenv.test`. The original edge remains running during cutover.

```bash
# Test standby before changing DNS
curl --resolve app.dotenv.test:443:10.7.8.224 https://app.dotenv.test/api/status
```

On both DNS servers, change the app record to `address=/app.dotenv.test/10.7.8.224`, validate and restart dnsmasq. Keep the TTL at 30 seconds. Remove any project hostname override in `/etc/hosts`.

```bash
sudo dnsmasq --test --conf-file="$(brew --prefix)/etc/dnsmasq.conf"
sudo brew services restart dnsmasq
dig @10.7.8.224 app.dotenv.test +short
dig @10.7.15.7 app.dotenv.test +short
# After observing TTL behavior, flush the client cache if needed
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
curl -sS -o /dev/null -w 'Edge: %{remote_ip} HTTP: %{http_code}\n' https://app.dotenv.test/api/status
```

Expected: edge `10.7.8.224`, HTTP 200. On Satvik's Mac, run `sudo nginx -s quit` to stop only the old edge; keep Backend B and backup DNS running. Repeat the HTTPS and load-balancing tests. Roll back by starting the original nginx, verifying it with `curl --resolve`, restoring both DNS records to `10.7.15.7`, and allowing caches to expire.

## Extension F — Faculty-Injected Troubleshooting Challenge

Diagnose the first failing layer instead of changing multiple settings at once. Explain the evidence aloud, fix the fault, and repeat the original request.

| Failure | Affected layer and why | Diagnostic / recovery |
|---|---|---|
| Wrong DNS server | DNS (application layer): resolver cannot answer the private name | `scutil --dns`; query both project resolvers with `dig @IP`; restore resolver settings |
| Wrong DNS A record | DNS: lookup succeeds but returns an incorrect destination | `dig @10.7.8.224 app.dotenv.test`; correct both DNS records |
| Stale DNS answer | DNS caching: previous answer remains valid until TTL expiry | Compare direct DNS and `dscacheutil -q host -a name app.dotenv.test`; wait or flush |
| Primary DNS stopped | DNS service availability: no response from primary | Query backup directly; restart primary after testing |
| LAN disconnected / wrong IP | Network/link: packets cannot reach the intended host | `ipconfig getifaddr en0`; `ping`; `route -n get 10.7.15.7` |
| Wrong destination port | TCP/transport: no listener at the requested endpoint | `nc -vz 10.7.15.7 443`; correct port |
| Firewall drops traffic | Network/transport filtering: TCP handshake cannot complete | Inspect PF rules and counters; restore intended allow rules |
| nginx stopped | Edge service availability, observed at TCP: HTTPS listener absent | `sudo lsof -nP -iTCP:443 -sTCP:LISTEN`; validate and start nginx |
| Certificate untrusted / hostname mismatch | TLS: TCP succeeds but peer authentication fails | `curl -v`; inspect certificate and install correct CA or certificate |
| One backend stopped | Upstream application availability: nginx retries healthy backend | Check port 3001 and repeated HTTPS requests; restart A |
| Both backends stopped | Upstream application availability: nginx cannot obtain a response, typically HTTP 502 | Test both backend ports; restart both |
| Wrong upstream IP/port | Proxy configuration: client HTTPS works but upstream TCP fails | `sudo nginx -T`; test upstream directly; correct and reload |
| Unexpected HTTP 404/501 | HTTP/application: server responds but path or method is unsupported | Use GET `/api/status`; inspect backend routes |
| ETag mismatch | HTTP caching: representation differs, so HTTP 200 is valid | Compare ETags on the same backend and retry conditional GET |

### Final demonstration sequence (Section 8)

1. Show topology, IP addresses and service inventory.
2. Verify LAN connectivity in both directions.
3. Resolve the private domain using project DNS.
4. Access HTTPS without bypassing certificate validation.
5. Show both `X-Backend` values using repeated requests.
6. Present DNS, TCP and TLS Wireshark captures.
7. Show Cache-Control, ETag and a conditional 304 response.
8. Stop Backend A, demonstrate HTTP 200 from B only, restart A and verify both return.
9. Demonstrate backup DNS, TTL and controlled edge migration.
10. Diagnose the faculty-injected fault layer by layer.
11. Answer individual viva questions.



---



## Team

**Team Name:** `DOTENV`

**Members:**

| Student | Roll number |
|---|---|
| Khushi Madan | 2401010225 |
| Satvik Prasad | 2401020055 |

**Project Domain:**

```text
app.dotenv.test
api.dotenv.test
```

