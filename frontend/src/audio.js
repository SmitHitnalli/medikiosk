let activePlayback = null;

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
