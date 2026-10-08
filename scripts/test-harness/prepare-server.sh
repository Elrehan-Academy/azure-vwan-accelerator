#!/usr/bin/env bash
set -euo pipefail

command -v python3 >/dev/null
mkdir -p /var/lib/vwan-harness
printf 'vwan-harness-server\n' > /var/lib/vwan-harness/index.html

for port in 8080 8081; do
    cat > "/etc/systemd/system/vwan-harness-${port}.service" <<EOF
[Unit]
Description=vWAN test HTTP listener ${port}
After=network.target

[Service]
User=nobody
ExecStart=/usr/bin/python3 -m http.server ${port} --bind 0.0.0.0 --directory /var/lib/vwan-harness
Restart=on-failure
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
done

chmod 755 /var/lib/vwan-harness
chmod 644 /var/lib/vwan-harness/index.html
systemctl daemon-reload
systemctl enable --now vwan-harness-8080.service vwan-harness-8081.service

python3 - <<'PY'
import time
import urllib.request

for port in (8080, 8081):
    for attempt in range(10):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/", timeout=3
            ) as response:
                body = response.read().decode().strip()
                assert body == "vwan-harness-server"
            print(f"PASS: local HTTP listener on port {port}")
            break
        except Exception:
            if attempt == 9:
                raise
            time.sleep(1)
print("SERVER_READY")
PY
