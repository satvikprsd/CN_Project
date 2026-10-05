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

The system is fully local. No cloud hosting is required.

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
| Mac 1 | Primary DNS, Backend A, Client | `dnsmasq :53`, Backend A `:3001` |
| Mac 2 | nginx Edge, Backend B, Client | nginx `:443` / `:8443`, Backend B `:3002` |

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
        |  10.7.22.85   |           |  10.7.30.220   |
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
app.dotenv.test  →  10.7.22.85
api.dotenv.test  →  10.7.30.220
```

The client connects to the nginx edge by domain name. It does not connect directly to either backend.

---


---

# Network Configuration

Record the actual values used by your team:

```text
Mac 1 IP = 10.7.22.85
Mac 2 IP =10.7.30.220

Primary DNS = 10.7.22.85:53
nginx Edge  = 10.7.30.220:443 or :8443

Backend A = 10.7.22.85:3001
Backend B = 10.7.30.220:3002
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
ping -c 4 10.7.22.85
```

### Mac 2

```bash
ping -c 4 10.7.30.220
```

---

# Private DNS — dnsmasq

Mac 1 runs the primary private DNS service.

Example configuration:

```conf
port=53
listen-address=10.7.22.85

no-resolv

server=1.1.1.1
server=8.8.8.8

address=/app.dotenv.test/10.7.30.220
address=/api.dotenv.test/10.7.30.220

no-hosts

cache-size=1000
log-queries
```

## Test the configuration

```bash
dnsmasq --test --conf-file="$(brew --prefix dnsmasq)/etc/dnsmasq.conf"
```

## Start dnsmasq

```bash
sudo brew services start dnsmasq
```

## Test the project DNS record

```bash
dig @10.7.22.85 app.dotenv.test
```

or:

```bash
nslookup app.dotenv.test 10.7.22.85
```

Expected result:

```text
app.dotenv.test → 10.7.30.220
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
    server 10.7.22.85:3001;
    server 10.7.30.220:3002;
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
nginx -t -c "$(brew --prefix nginx)/etc/nginx/nginx.conf"
```

## Start nginx

```bash
nginx -c "$(brew --prefix nginx)/etc/nginx/nginx.conf"
```

## Reload nginx

```bash
nginx -s reload
```

---

# Load Balancing Test

Run repeated requests through the domain:

```bash
for i in {1..10}; do
    curl -si https://app.dotenv.test/api/status | grep -E "HTTP/|X-Backend"
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
curl -I https://app.dotenv.test/
```

Conditional request example:

```bash
curl -i \
  -H 'If-None-Match: "abc123"' \
  https://app.dotenv.test/
```

Expected conditional response:

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
Answer: 10.7.30.220
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
Certificate
Key Exchange
Finished
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
   10.7.30.220

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
nc -vz 10.7.30.220 443
```

or:

```bash
nc -vz 10.7.30.220 8443
```

## Check TLS

```bash
curl -v https://app.dotenv.test/api/status
```

## Check the backends directly

```bash
curl http://10.7.22.85:3001/api/status
curl http://10.7.30.220:3002/api/status
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

Run a second DNS resolver on the other Mac and configure clients with both DNS server addresses.

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

so that only nginx can reach them.

## Backend Failover

Stop Backend A and confirm that nginx continues serving Backend B.

Restart Backend A and verify that load balancing resumes.

## Edge Migration

Use a standby nginx edge and change the DNS record to move the service to the standby machine.



---



## Team

**Team Name:** `dotenv`

**Members:**

- `Khushi`
- `Satvik Prasad`

**Project Domain:**

```text
app.dotenv.test
api.dotenv.test
```

