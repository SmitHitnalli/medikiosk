let activePlayback = null;
// Remembers the most recently played prompt audio so a global "repeat" control
// (see AccessibilityBar) can replay it on any screen without each screen having
// to wire up its own repeat logic. The Blob itself stays valid after playback -
// only its object URL gets revoked - so it's safe to keep and replay later.
let lastSpokenBlob = null;

export function hasRepeatableAudio() {
  return lastSpokenBlob !== null;
}

export function clearRepeatAudio() {
  stopAllAudio();
  lastSpokenBlob = null;
}

export function repeatLastAudio() {
  if (!lastSpokenBlob) return Promise.resolve();
  return playAudioBlob(lastSpokenBlob);
}

export function stopAllAudio() {
  if (activePlayback) {
    const playback = activePlayback;
    activePlayback = null;
    playback.audio.pause();
    playback.audio.currentTime = 0;
    URL.revokeObjectURL(playback.url);
    playback.reject(new Error("Audio playback stopped."));
  }
  window.speechSynthesis?.cancel();
}

export function playAudioBlob(blob) {
  stopAllAudio();
  lastSpokenBlob = blob;
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    const finish = (error) => {
      if (activePlayback?.audio === audio) activePlayback = null;
      URL.revokeObjectURL(url);
      if (error) reject(error);
      else resolve();
    };
    activePlayback = { audio, url, reject: (error) => finish(error) };
    audio.onended = () => finish();
    audio.onerror = () => finish(new Error("The audio could not be played."));
    audio.play().catch(finish);
  });
}
