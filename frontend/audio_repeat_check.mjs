// Guards Phase 5 item 8 (repeat-last-prompt staleness): clearRepeatAudio must
// actually reset hasRepeatableAudio(), since App.jsx relies on it to drop a
// stale Speak-mode prompt when the patient switches to Chat mode.
// Run: node audio_repeat_check.mjs
import assert from "node:assert/strict";

global.window = global;
global.window.speechSynthesis = { cancel() {} };
global.URL.createObjectURL = () => "blob://fake";
global.URL.revokeObjectURL = () => {};
global.Audio = class {
  play() { return Promise.resolve(); }
  pause() {}
};

const { hasRepeatableAudio, clearRepeatAudio, playAudioBlob } = await import("./src/audio.js");

assert.equal(hasRepeatableAudio(), false, "no prompt has played yet");

const playback = playAudioBlob(new Blob(["fake audio"]));
assert.equal(hasRepeatableAudio(), true, "a prompt just played, so it must be repeatable");

clearRepeatAudio();
assert.equal(hasRepeatableAudio(), false, "clearRepeatAudio must drop the stale prompt");

await playback.catch(() => {}); // clearRepeatAudio's stopAllAudio() rejects the in-flight play()

console.log("audio_repeat_check: clearRepeatAudio correctly resets hasRepeatableAudio()");
