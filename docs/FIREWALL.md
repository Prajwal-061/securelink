# SecureLink Firewall Guidance

SecureLink needs:
- TCP listen port (default `5000`, configurable)
- UDP discovery port `5556`

Do not auto-modify firewalls silently in production. Use explicit admin-approved commands.

## Windows (Run As Administrator)

```powershell
netsh advfirewall firewall add rule name="SecureLink TCP 5000" dir=in action=allow protocol=TCP localport=5000
netsh advfirewall firewall add rule name="SecureLink UDP 5556" dir=in action=allow protocol=UDP localport=5556
```

If you run on a different TCP port, replace `5000` with that port.

To remove rules later:

```powershell
netsh advfirewall firewall delete rule name="SecureLink TCP 5000"
netsh advfirewall firewall delete rule name="SecureLink UDP 5556"
```

## Linux (UFW)

```bash
sudo ufw allow 5000/tcp
sudo ufw allow 5556/udp
sudo ufw reload
```

If UFW is not used, adapt commands for `firewalld` or raw `iptables`.

## Router / LAN Requirements

- Ensure all demo devices are on the same LAN segment.
- Disable AP/client isolation on the Wi-Fi access point.
- Avoid captive portals and enterprise client isolation policies.
