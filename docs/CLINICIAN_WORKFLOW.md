# Clinician review workflow

The physician view is the approval boundary between patient-collected history and any downstream record export.

1. A doctor or administrator opens a patient session.
2. They correct the structured complaint, medicines, allergies, and history fields and record a reason. Each save creates an immutable numbered revision.
3. Ayurveda practitioner confirmation is also versioned and clears any older signature.
4. The clinician checks the attestation and signs off. The server stores a signed snapshot and a SHA-256 signature over the canonical clinical data, clinician identity, and time.
5. Patient and clinician PDF buttons become available. The patient copy is plain-language and omits internal detail; the clinician copy includes the full review and signature.
6. ABDM/HIS export is rejected until the current record has a valid sign-off. Any later edit deletes the old sign-off and prior export.

Handwritten documents are selected explicitly during capture and routed to staff review. OCR text and starter-formulary matches are suggestions only. They never become a prescription or confirmed medication without clinician review. The included formulary is a small demonstration list and must be replaced with the hospital's governed drug terminology before clinical deployment.
