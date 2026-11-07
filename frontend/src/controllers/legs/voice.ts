// Spoken prompts for pocket play: the phone is out of sight, so instructions are audio.
// iOS only allows audio after a user gesture, so call unlock() synchronously inside a tap first.

let audio: AudioContext | null = null

export function unlockAudio(): void {
  try {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!audio && Ctor) audio = new Ctor()
    void audio?.resume()
    // Speaking an empty utterance inside the gesture unlocks later speech on iOS.
    window.speechSynthesis?.speak(new SpeechSynthesisUtterance(''))
  } catch {
    // Audio is guidance only; the controller still works silently.
  }
}

export function beep(freq = 880, ms = 120): void {
  try {
    if (!audio) return
    const osc = audio.createOscillator()
    const gain = audio.createGain()
    osc.frequency.value = freq
    gain.gain.value = 0.2
    osc.connect(gain).connect(audio.destination)
    osc.start()
    osc.stop(audio.currentTime + ms / 1000)
  } catch {
    // ignore
  }
}

export function say(text: string): void {
  try {
    window.speechSynthesis?.cancel()
    window.speechSynthesis?.speak(new SpeechSynthesisUtterance(text))
  } catch {
    // ignore
  }
}

export function silence(): void {
  try {
    window.speechSynthesis?.cancel()
  } catch {
    // ignore
  }
}
