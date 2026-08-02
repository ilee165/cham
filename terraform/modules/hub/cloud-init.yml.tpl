#cloud-config
# Hub DDI VM: WireGuard endpoint + BIND9 conditional forwarder.
# NVA requirement #2 of 2: ip_forward in the guest (NIC flag is in Terraform).
package_update: true
packages:
  - wireguard
  - bind9
  - bind9-utils
  - iptables-persistent

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
      Address = 172.16.0.1/24
      ListenPort = 51820

      [Peer]
      # Laptop
      PublicKey = ${wg_peer_public_key}
      AllowedIPs = 172.16.0.2/32, ${onprem_cidr}

  - path: /etc/bind/named.conf.options
    content: |
      options {
        directory "/var/cache/bind";
        recursion yes;
        allow-query { 10.10.0.0/16; ${onprem_cidr}; ${wg_transfer_cidr}; localhost; };
        allow-recursion { 10.10.0.0/16; ${onprem_cidr}; ${wg_transfer_cidr}; localhost; };
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
      if ! iptables -t nat -C POSTROUTING -s 10.10.0.0/16 ! -d 10.0.0.0/8 -o "$outbound_interface" -j MASQUERADE 2>/dev/null; then
        iptables -t nat -A POSTROUTING -s 10.10.0.0/16 ! -d 10.0.0.0/8 -o "$outbound_interface" -j MASQUERADE
      fi
      netfilter-persistent save

runcmd:
  - sysctl --system
  - /usr/local/sbin/configure-cham-nat
  - systemctl enable --now bind9 || systemctl enable --now named
  # WireGuard left disabled until a real private key is installed:
  - systemctl disable --now wg-quick@wg0 || true
  - >-
    echo "Run 'wg genkey' on this host, patch wg0.conf, then:
    systemctl enable --now wg-quick@wg0"
