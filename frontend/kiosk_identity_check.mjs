// Guards Phase 5 item 12: the kiosk's own identifier must never be rendered
// on a patient-facing screen, but must be visible to staff on the Device
// Check screen so a technician can tell which physical machine they're at.
// Run: node kiosk_identity_check.mjs
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const srcDir = new URL("./src/", import.meta.url);
const files = readdirSync(srcDir).filter((name) => name.endsWith(".jsx") || name.endsWith(".js"));

const ALLOWED_REFERENCES = new Set(["api.js", "DeviceDiagnostics.jsx"]);

for (const file of files) {
  const contents = readFileSync(new URL(file, srcDir), "utf8");
  if (contents.includes("KIOSK_ID")) {
    assert.ok(ALLOWED_REFERENCES.has(file), `${file} references KIOSK_ID but is not an allowed (staff-only) surface`);
  }
}

const deviceDiagnostics = readFileSync(new URL("DeviceDiagnostics.jsx", srcDir), "utf8");
assert.match(deviceDiagnostics, /KIOSK_ID/, "Device Check screen must display the kiosk's own identifier for staff");

console.log("kiosk_identity_check: KIOSK_ID is staff-only (Device Check) and absent from every other screen");
