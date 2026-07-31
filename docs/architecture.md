# Architecture

(Copy the diagram + resolution-path table from the build plan here, and
replace with a rendered draw.io/mermaid diagram before the repo goes
public. This file is what the README links to first.)

## Addressing
| Block | Purpose |
|---|---|
| 10.20.0.0/16 | On-prem (SpatiumDDI-served) |
| 10.10.0.0/16 | Azure supernet |
| 10.10.0.0/22 | Hub VNet |
| 10.10.4.0/22 | Spoke A (app) |
| 10.10.8.0/22 | Spoke B (mgmt) |
| 172.16.0.0/24 | WireGuard transfer net |

## DNS zones
| Zone | Authority | Managed by |
|---|---|---|
| dwsolution.co (public) | Cloudflare | Terraform infrastructure/seeds + reconciler-owned record set |
| lab.dwsolution.co | Laptop BIND9 (SpatiumDDI) | SpatiumDDI |
| azure.dwsolution.co | Azure Private DNS | Terraform seeds + reconciler |
| www.dwsolution.co (internal view) | BIND9 override | SpatiumDDI |
