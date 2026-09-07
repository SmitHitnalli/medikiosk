"""Production-style launcher with explicit TLS configuration."""

import os
from pathlib import Path

import uvicorn


def main() -> None:
    cert = os.environ.get("TLS_CERT_FILE", "").strip()
    key = os.environ.get("TLS_KEY_FILE", "").strip()
    if bool(cert) != bool(key):
        raise SystemExit("Set both TLS_CERT_FILE and TLS_KEY_FILE, or neither for local development")
    if cert and (not Path(cert).is_file() or not Path(key).is_file()):
        raise SystemExit("The configured TLS certificate or key file does not exist")
    uvicorn.run(
        "main:app", host=os.environ.get("MEDIKIOSK_HOST", "0.0.0.0"),
        port=int(os.environ.get("MEDIKIOSK_PORT", "8080")),
        ssl_certfile=cert or None, ssl_keyfile=key or None,
        proxy_headers=True, forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )


if __name__ == "__main__":
    main()
