# SpatiumDDI — local stack

Follow the upstream Docker Compose quick start:
https://github.com/spatiumddi/spatiumddi

Then the Getting Started ordering (dependencies are real — do it in order):
1. Platform settings
2. DNS server groups + servers (bundled BIND9)
3. DNS zones — forward `lab.dwsolution.co` first, then reverse `20.10.in-addr.arpa`
4. DHCP server groups + servers (bundled Kea)
5. IPAM IP Space: 10.20.0.0/16 (on-prem) AND 10.10.0.0/16 (Azure — modeled, not served)
6. IP Blocks, then Subnets — pin DNS + DHCP groups at the subnet or inherit

Phase 1 exit test: a Kea DHCP lease produces an A record in BIND9, and
`dig -p 1053 @127.0.0.1 printer.lab.dwsolution.co` answers.

The bundled agent publishes on host port **1053**, not 53 (compose default,
to avoid colliding with anything already bound to 53). Plain `@localhost`
queries the host's own resolver and tells you nothing about this stack.

Bring the DNS agent up with the group override — upstream hardcodes
`AGENT_GROUP: default`, which makes the agent auto-create an empty `default`
group and join that instead of `primary`:

```bash
cd ../spatiumddi
docker compose -f docker-compose.yml -f ../spatium/docker-compose.agent-group.yml \
  --profile dns-bind9 up -d
```

Set `DNS_AGENT_KEY` to a non-empty value in `spatiumddi/.env` first. Left
empty, the control plane rejects registration with `503 DNS_AGENT_KEY is not
configured` while the agent falls back to a compose default — both sides look
configured and neither matches.

A DNS group's `catalog_zone_name` must not name a zone that group also
serves, or the rendered `named.conf` declares it twice and `named-checkconf`
fails. The agent reports that failure with an empty error message; see the
A3 notes in `docs/superpowers/plans/2026-07-31-phase-4-cloudflare-reconciler-v2.md`
for how to read the real one.

Pin the compose file / image tags here once you pick a release — don't track
`latest` in a lab you'll demo from.
