# ABDM integration

MediKiosk keeps its hospital-local Medi ID and can optionally link it to a verified ABHA number/address. A patient may provide ABHA details during registration, but that record remains `patient_provided` until a doctor/admin records the QR, OTP, demographic-match, or Sandbox verification reference. Full ABHA numbers are masked in API responses and never placed in logs.

## Modes

- `ABDM_MODE=local` builds and validates the exact document contract, stores care contexts and consent workflow state, and never claims network delivery.
- `ABDM_MODE=sandbox` becomes available only when the base URL, client credentials, bridge ID, facility data, and assigned M1/M2/M3 paths are configured. Failed gateway delivery returns an error rather than silently falling back to local mode.

The doctor workflow signs the clinical record before creating a care context. Export builds a FHIR R4 `Bundle.type=document` with the NRCeS `DocumentBundle` profile, an `OPConsultRecord` Composition as the first entry, and absolute `urn:uuid` references. A local validator rejects missing mandatory document invariants. CI/deployment must additionally run the official HL7 validator with the current NRCeS package.

## Milestone mapping

- M1: optional ABHA capture plus a verified hybrid Medi ID/ABHA link. OTP secrets are never stored. Actual OTP/QR verification must use the facility's assigned Sandbox APIs.
- M2 HIP: signed visits create care contexts; authenticated consent callbacks are persisted; the export boundary prepares the validated OP consultation document. ABDM encryption and data-transfer delivery must be completed through the registered bridge using consent-artifact key material.
- M3 HIU: staff can create bounded consent requests; consent and health-information notifications are stored as metadata and audited. Raw inbound health data is deliberately not accepted into the clinical record until decryption, signature verification, provenance mapping, and a clinician review screen are supplied by the registered bridge.

Official references:

- [ABDM Sandbox integration and exit process](https://docs.coronasafe.network/abdm-documentation/implementers-guide/abdm-sandbox-integration-and-exit-process)
- [ABDM M2 HIP feature requirements](https://docs.coronasafe.network/abdm-documentation/abha-number-service-or-milestone-2/features-covered)
- [NRCeS FHIR R4 implementation guide](https://nrces.in/ndhm/fhir/r4/index.html)
- [NRCeS FHIR package](https://nrces.in/ndhm/fhir/r4/package.tgz)

Production access also requires Sandbox registration, HFR facility linkage, functional certification, and STQC or CERT-In empanelled security testing described by ABDM. These are organization-level dependencies rather than application flags.
