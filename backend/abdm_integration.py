"""ABDM transport boundary and local FHIR document validation.

Network paths are configuration, because ABDM sandbox versions and assigned bridge
routes vary by integrator. The client refuses live calls until credentials exist.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field


class AbdmConfigurationError(RuntimeError):
    pass


class AbdmTransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class AbdmConfig:
    mode: str = field(default_factory=lambda: os.environ.get("ABDM_MODE", "local").strip().lower())
    base_url: str = field(default_factory=lambda: os.environ.get("ABDM_BASE_URL", "").rstrip("/"))
    client_id: str = field(default_factory=lambda: os.environ.get("ABDM_CLIENT_ID", ""))
    client_secret: str = field(default_factory=lambda: os.environ.get("ABDM_CLIENT_SECRET", ""))
    bridge_id: str = field(default_factory=lambda: os.environ.get("ABDM_BRIDGE_ID", ""))
    facility_id: str = field(default_factory=lambda: os.environ.get("ABDM_FACILITY_ID", ""))
    facility_name: str = field(default_factory=lambda: os.environ.get("ABDM_FACILITY_NAME", "MediKiosk Demo Facility"))
    session_path: str = field(default_factory=lambda: os.environ.get("ABDM_SESSION_PATH", "/api/hiecm/gateway/v3/sessions"))
    hip_notify_path: str = field(default_factory=lambda: os.environ.get("ABDM_HIP_NOTIFY_PATH", ""))
    hiu_consent_path: str = field(default_factory=lambda: os.environ.get("ABDM_HIU_CONSENT_PATH", ""))

    @property
    def live_ready(self) -> bool:
        return self.mode == "sandbox" and all((self.base_url, self.client_id, self.client_secret, self.bridge_id))

    def public_status(self) -> dict:
        return {
            "mode": self.mode,
            "live_ready": self.live_ready,
            "bridge_configured": bool(self.bridge_id),
            "facility_configured": bool(self.facility_id),
        }


class AbdmClient:
    def __init__(self, config: AbdmConfig | None = None):
        self.config = config or AbdmConfig()
        self._token = ""
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def _session_token(self) -> str:
        if not self.config.live_ready:
            raise AbdmConfigurationError("ABDM sandbox credentials are not configured")
        with self._lock:
            if self._token and self._expires_at > time.time() + 30:
                return self._token
            payload = {"clientId": self.config.client_id, "clientSecret": self.config.client_secret, "grantType": "client_credentials"}
            result = self._request(self.config.session_path, payload, authenticated=False)
            self._token = str(result.get("accessToken") or result.get("access_token") or "")
            if not self._token:
                raise AbdmTransportError("ABDM session response did not contain an access token")
            self._expires_at = time.time() + int(result.get("expiresIn") or result.get("expires_in") or 300)
            return self._token

    def _request(self, path: str, payload: dict, authenticated: bool = True) -> dict:
        if not path:
            raise AbdmConfigurationError("The required ABDM API path is not configured")
        headers = {
            "Content-Type": "application/json",
            "REQUEST-ID": str(uuid.uuid4()),
            "TIMESTAMP": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "X-CM-ID": "sbx" if self.config.mode == "sandbox" else "abdm",
        }
        if authenticated:
            headers["Authorization"] = f"Bearer {self._session_token()}"
            headers["X-HIP-ID"] = self.config.bridge_id
        request = urllib.request.Request(
            self.config.base_url + "/" + path.lstrip("/"),
            data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AbdmTransportError(f"ABDM request failed: {exc}") from exc

    def notify_care_context(self, payload: dict) -> dict:
        return self._request(self.config.hip_notify_path, payload)

    def create_hiu_consent_request(self, payload: dict) -> dict:
        return self._request(self.config.hiu_consent_path, payload)


def validate_document_bundle(bundle: dict) -> list[str]:
    """Fast local gate for mandatory ABDM document invariants.

    Full profile validation still belongs in CI using the official NRCeS package.
    """
    errors = []
    if bundle.get("resourceType") != "Bundle": errors.append("resourceType must be Bundle")
    if bundle.get("type") != "document": errors.append("Bundle.type must be document")
    profiles = (bundle.get("meta") or {}).get("profile") or []
    if "https://nrces.in/ndhm/fhir/r4/StructureDefinition/DocumentBundle" not in profiles:
        errors.append("DocumentBundle profile is missing")
    entries = bundle.get("entry") or []
    if not entries or (entries[0].get("resource") or {}).get("resourceType") != "Composition":
        errors.append("The first entry must be a Composition")
    full_urls = [entry.get("fullUrl") for entry in entries]
    if any(not value or not value.startswith("urn:uuid:") for value in full_urls):
        errors.append("Every entry needs an absolute urn:uuid fullUrl")
    if len(full_urls) != len(set(full_urls)): errors.append("Bundle entry fullUrls must be unique")
    resources = {(entry.get("resource") or {}).get("resourceType") for entry in entries}
    for required in ("Composition", "Patient", "Encounter", "Practitioner", "Organization"):
        if required not in resources: errors.append(f"{required} resource is missing")
    return errors
