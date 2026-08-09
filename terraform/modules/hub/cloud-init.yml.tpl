#cloud-config
# Hub DDI VM: WireGuard endpoint + BIND9 conditional forwarder.
# NVA requirement #2 of 2: ip_forward in the guest (NIC flag is in Terraform).
package_update: true
packages:
  - wireguard
  - bind9
  - bind9-utils
  - iptables-persistent
  - nginx

write_files:
  - path: /etc/sysctl.d/99-forwarding.conf
    content: |
      net.ipv4.ip_forward=1

  - path: /etc/wireguard/wg0.conf
    permissions: "0600"
    content: |
      [Interface]
      # Generate on first boot: wg genkey — do NOT commit real keys
      PrivateKey = REPLACE_ON_HOST
      Address = ${wg_interface_cidr}
      ListenPort = 51820

      [Peer]
      # Laptop
      PublicKey = ${wg_peer_public_key}
      AllowedIPs = ${onprem_dns_ip}/32, ${onprem_cidr}

  - path: /etc/bind/named.conf.options
    content: |
      options {
        directory "/var/cache/bind";
        recursion yes;
        allow-query { ${join("; ", internal_cidrs)}; ${onprem_cidr}; ${wg_transfer_cidr}; localhost; };
        allow-recursion { ${join("; ", internal_cidrs)}; ${onprem_cidr}; ${wg_transfer_cidr}; localhost; };
        // Default path: Azure-provided DNS (Private DNS zones resolve here)
        forwarders { 168.63.129.16; };
        forward only;
        dnssec-validation no;  // 168.63.129.16 doesn't serve DNSSEC for private zones
      };

  - path: /etc/bind/named.conf.local
    content: |
      // On-prem lab zone -> laptop BIND9 across the tunnel
      zone "${lab_zone}" {
        type forward;
        forward only;
        forwarders { ${onprem_dns_ip}; };
      };

  - path: /usr/local/sbin/configure-cham-nat
    permissions: "0755"
    content: |
      #!/bin/sh
      set -eu
      outbound_interface="$(ip -4 route show default | awk '/default/ { for (i = 1; i <= NF; i++) if ($i == "dev") { print $(i + 1); exit } }')"
      if [ -z "$outbound_interface" ]; then
        echo "Unable to discover the default outbound interface" >&2
        exit 1
      fi
      # WR-02: sources and private destinations derive from the module inputs
      # instead of the old hard-coded lab-aggregate/RFC1918 `-s ... ! -d` pair.
      # iptables cannot express "not in {A,B,C}" in one rule, so traffic from
      # any internal network toward any private destination (internal,
      # on-prem, WireGuard transfer) RETURNs un-NATed first — inserted at the
      # top so they always precede the MASQUERADE — and everything else from
      # internal space masquerades out the default interface.
%{ for dst in concat(internal_cidrs, [onprem_cidr, wg_transfer_cidr]) ~}
%{ for src in internal_cidrs ~}
      if ! iptables -t nat -C POSTROUTING -s ${src} -d ${dst} -j RETURN 2>/dev/null; then
        iptables -t nat -I POSTROUTING -s ${src} -d ${dst} -j RETURN
      fi
%{ endfor ~}
%{ endfor ~}
%{ for src in internal_cidrs ~}
      if ! iptables -t nat -C POSTROUTING -s ${src} -o "$outbound_interface" -j MASQUERADE 2>/dev/null; then
        iptables -t nat -A POSTROUTING -s ${src} -o "$outbound_interface" -j MASQUERADE
      fi
%{ endfor ~}
      netfilter-persistent save

  - path: /var/www/html/index.html
    content: |
      <h1>INTERNAL — served from the hub over the tunnel</h1>

  # Overrides Debian's stock catch-all server block. Written ahead of the
  # nginx package install (write_files runs before packages), the same
  # ordering the plain index.html above already relies on — nginx's
  # postinst only creates sites-available/default when it is absent, so a
  # file already on disk survives the install untouched. Binding explicitly
  # to hub_vm_ip means the page is never reachable on any interface/address
  # other than the hub's private IP, regardless of what the NSG allows
  # (defense in depth for CR-3, since IPv6 is unused here the stock
  # "listen [::]:80" line is dropped rather than widened).
  - path: /etc/nginx/sites-available/default
    content: |
      server {
        listen ${hub_vm_ip}:80;

        root /var/www/html;
        index index.html;

        server_name _;

        location / {
          try_files $uri $uri/ =404;
        }
      }

runcmd:
  - sysctl --system
  - /usr/local/sbin/configure-cham-nat
  - systemctl enable --now bind9 || systemctl enable --now named
  - systemctl enable --now nginx
  # WireGuard left disabled until a real private key is installed:
  - systemctl disable --now wg-quick@wg0 || true
  - >-
    echo "Run 'wg genkey' on this host, patch wg0.conf, then:
    systemctl enable --now wg-quick@wg0"
