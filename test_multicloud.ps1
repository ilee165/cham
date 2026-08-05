$ErrorActionPreference = 'Stop'

$azureCliDir = 'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin'
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
  if (-not (Test-Path -LiteralPath (Join-Path $azureCliDir 'az.cmd'))) {
    throw 'Azure CLI was not found in PATH or its official install directory'
  }
  $env:Path = "$azureCliDir;$env:Path"
}

$terraform = (Get-Command terraform -ErrorAction Stop).Source
$terraformRoot = Join-Path $PSScriptRoot 'terraform\envs\lab'
if (-not (Test-Path -LiteralPath $terraformRoot)) {
  throw "Terraform lab root was not found: $terraformRoot"
}

$SSH = @(
  'C:\Windows\System32\OpenSSH\ssh.exe',
  'C:\Windows\Sysnative\OpenSSH\ssh.exe'
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

$sshKey     = Join-Path $env:USERPROFILE '.ssh\cham_lab_ed25519'
$privateKey = Join-Path $env:USERPROFILE '.wg\cham-laptop.key'
$publicKey  = Join-Path $env:USERPROFILE '.wg\cham-laptop.pub'

$hubIpRaw = & $terraform "-chdir=$terraformRoot" output -raw hub_public_ip
if ($LASTEXITCODE -ne 0) {
  throw "Terraform could not read hub_public_ip (exit code $LASTEXITCODE)"
}
if ([string]::IsNullOrWhiteSpace($hubIpRaw)) {
  throw 'Terraform returned an empty hub_public_ip'
}
$hubIp = $hubIpRaw.Trim()

$hubPublic = (
  & $SSH -i $sshKey -o IdentitiesOnly=yes -o BatchMode=yes `
    "labadmin@$hubIp" `
    'sudo sh -c "wg pubkey </etc/wireguard/hub.key"'
).Trim()

if ($hubIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
  throw 'Unexpected hub endpoint format'
}
if ($hubPublic -notmatch '^[A-Za-z0-9+/]{43}=$') {
  throw 'Unexpected hub public-key format'
}

# Operator-only transfer into the WSL filesystem; nothing is printed.
$laptopPrivate = (Get-Content -LiteralPath $privateKey -Raw).Trim()
$laptopPrivate | wsl.exe -d Debian -u root -- bash -lc `
  'install -d -m 700 -o root -g root /etc/wireguard; umask 077; tr -d ''\r\n'' >/etc/wireguard/cham-laptop.key; chown root:root /etc/wireguard/cham-laptop.key; chmod 600 /etc/wireguard/cham-laptop.key'
$laptopPrivate = $null

$configTemplate = @'
set -euo pipefail
private="$(cat /etc/wireguard/cham-laptop.key)"
cat >/etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 172.16.0.2/24
PrivateKey = $private
PostUp = iptables -t nat -C POSTROUTING -o %i -j MASQUERADE || iptables -t nat -A POSTROUTING -o %i -j MASQUERADE
PostDown = iptables -t nat -C POSTROUTING -o %i -j MASQUERADE && iptables -t nat -D POSTROUTING -o %i -j MASQUERADE || true

[Peer]
PublicKey = __HUB_PUBLIC__
Endpoint = __HUB_IP__:51820
AllowedIPs = 172.16.0.0/24, 10.10.0.0/16
PersistentKeepalive = 25
EOF
unset private
chown root:root /etc/wireguard/wg0.conf
chmod 600 /etc/wireguard/wg0.conf
wg-quick strip /etc/wireguard/wg0.conf >/dev/null
sysctl -w net.ipv4.ip_forward=1 >/dev/null
test "$(stat -c '%U:%G:%a' /etc/wireguard/wg0.conf)" = root:root:600
'@

$configScript = $configTemplate.
  Replace('__HUB_PUBLIC__', $hubPublic).
  Replace('__HUB_IP__', $hubIp)

$configScript | wsl.exe -d Debian -u root -- bash -lc 'tr -d ''\r'' | bash -s'
if ($LASTEXITCODE -ne 0) {
  throw 'WireGuard configuration failed'
}

$storedPublic = (Get-Content -LiteralPath $publicKey -Raw).Trim()
$derivedPublic = (
  wsl.exe -d Debian -u root -- bash -lc `
    'sh -c "wg pubkey </etc/wireguard/cham-laptop.key"'
).Trim()

[ordered]@{
  operator_key_match = ($derivedPublic -eq $storedPublic)
  config_mode_ok     = $true
  config_syntax_ok   = $true
} | ConvertTo-Json
