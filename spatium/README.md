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
`dig @localhost printer.lab.dwsolution.co` answers.

Pin the compose file / image tags here once you pick a release — don't track
`latest` in a lab you'll demo from.
