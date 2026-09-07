# Speech provider setup

MediKiosk has one stable patient API and three interchangeable speech backends.
Set `SPEECH_PROVIDER` in `backend/.env` to `local`, `bhashini`, or `ai4bharat`.
If a remote call is unavailable or malformed, the request automatically falls
back to local faster-whisper for speech recognition and Piper for speech output.
The response identifies the provider used so deployment monitoring can detect a
fallback without interrupting the patient.

## Local

This is the default and needs no network connection. English and Hindi use the
existing faster-whisper and Piper models. The language-selection recording stays
local because a language has not been chosen yet.

## Bhashini

Bhashini requires a Pipeline Config call before compute calls. Copy its returned
`callbackURL`, authentication header name/value, and the chosen ASR/TTS service
IDs into the `BHASHINI_*` variables shown in `backend/.env.example`. MediKiosk
then sends the official `pipelineTasks` and `inputData` compute payloads.

Official documentation:

- https://dibd-bhashini.gitbook.io/bhashini-apis
- https://dibd-bhashini.gitbook.io/bhashini-apis/pipeline-compute-call

The public API terms describe this access as proof-of-concept use. Contact the
Bhashini team for production or paid deployment terms.

## Self-hosted AI4Bharat

Run the IndicConformer ASR service and set `AI4BHARAT_ASR_URL` to its base URL.
MediKiosk uses the project's `/recognize/{language}` JSON/base64 contract.

- https://github.com/AI4Bharat/indic-asr-api-backend

IndicF5 is a model library rather than a ready HTTP service. Deploy a small
private wrapper that accepts `{ "text", "language", "format": "wav" }` and
returns `{ "audio": "<base64 wav>" }`, then set `AI4BHARAT_TTS_URL`.

- https://github.com/AI4Bharat/IndicF5

The Speak interface already stops current playback when the patient starts
talking, stops recording after silence, shows state and captions, and always
offers typed input. True partial-transcript streaming depends on the selected
provider exposing a streaming protocol and should be enabled only after the
actual service and kiosk microphone have been benchmarked.
