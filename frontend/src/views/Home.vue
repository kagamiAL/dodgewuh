<script setup lang="ts">
import { ref } from 'vue'
import StadiumBackground from '@/components/StadiumBackground.vue'
import { useRouter } from 'vue-router'
import type { Device } from '@/contracts/pending'
import { createRoom, joinRoom, leave } from '@/stores/connection'

const router = useRouter()
const isTouch = typeof window !== 'undefined' && window.matchMedia('(pointer: coarse)').matches

const name = ref('')
const code = ref('')
const device = ref<Device>(isTouch ? 'phone' : 'screen')
const busy = ref(false)
const error = ref('')

async function run(action: () => Promise<unknown>, to: string): Promise<void> {
  if (busy.value) return
  error.value = ''
  busy.value = true
  try {
    leave() // one membership per tab
    await action()
    // Phones load /phone as a fresh document: iOS Shake to Undo offers "Undo Typing" for anything
    // typed earlier in the same document (the code/name fields here), and an Arms throw is a shake.
    // The registration survives in sessionStorage and PhoneShell connects with it on mount.
    if (to === '/phone' && registrationSaved()) {
      window.location.assign(to)
      return
    }
    await router.push(to)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

// Private mode can block storage; then a reload would lose the registration, so stay in-app.
function registrationSaved(): boolean {
  try {
    return sessionStorage.getItem('dodgewuh.registration') !== null
  } catch {
    return false
  }
}

function displayName(fallback: string): string {
  return name.value.trim().slice(0, 24) || fallback
}

const create = () => run(() => createRoom(displayName('Main screen')), '/screen')
const join = () =>
  run(
    () => joinRoom(code.value, displayName(device.value === 'phone' ? 'Player' : 'Screen'), device.value),
    device.value === 'phone' ? '/phone' : '/screen',
  )
</script>

<template>
  <main class="home">
    <StadiumBackground />
    <header class="intro">
      <h1>dodgewuhhh<span class="brand-period">!</span></h1>
      <p class="lede">It come with partnerrrr.</p>
      <div class="court-preview" role="img" aria-label="Two opposing teams on a dodgeball court. Each character is controlled by an Arms player and a Legs player.">
        <svg class="court" viewBox="0 0 480 230" aria-hidden="true">
          <rect x="12" y="12" width="456" height="206" rx="8" fill="#172c42" stroke="#557388" stroke-width="2" />
          <path d="M240 12V218" stroke="#8fa6b1" stroke-width="2" />
          <circle cx="240" cy="115" r="46" fill="none" stroke="#8fa6b1" stroke-width="2" />
          <path d="M12 65H64V165H12M468 65H416V165H468" fill="none" stroke="#557388" stroke-width="2" />
          <circle cx="122" cy="115" r="34" fill="#338cff" />
          <circle cx="358" cy="115" r="34" fill="#ff8c26" />
          <path d="M112 115H132M122 105V125M348 115H368M358 105V125" stroke="#101820" stroke-width="4" stroke-linecap="round" />
          <circle class="court-ball" cx="214" cy="91" r="10" fill="#fff5dc" stroke="#101820" stroke-width="3" />
          <circle cx="264" cy="160" r="6" fill="#fff5dc" />
          <text x="122" y="180" text-anchor="middle">TEAM 1</text>
          <text x="358" y="180" text-anchor="middle">TEAM 2</text>
        </svg>
        <div class="team-controls"><span>Arms + Legs</span><span>Arms + Legs</span></div>
      </div>
    </header>

    <div class="entry">

    <label class="field">
      <span>Your name <span class="optional">Optional</span></span>
      <input v-model="name" maxlength="24" autocomplete="nickname" placeholder="What should we call you?" />
    </label>

    <section class="card">
      <h2>Join a room</h2>
      <form @submit.prevent="join">
        <input
          v-model="code"
          id="room-code"
          aria-label="Room code"
          class="code"
          maxlength="6"
          autocapitalize="characters"
          autocomplete="off"
          spellcheck="false"
          placeholder="ROOM CODE"
          required
        />
        <div class="devices" role="radiogroup" aria-label="Device">
          <label :class="{ on: device === 'phone' }">
            <input v-model="device" type="radio" value="phone" /> Phone controller
          </label>
          <label :class="{ on: device === 'screen' }">
            <input v-model="device" type="radio" value="screen" /> Screen
          </label>
        </div>
        <button type="submit" :disabled="busy || code.trim().length !== 6">{{ busy ? 'Connecting…' : 'Join room' }}<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg></button>
      </form>
    </section>

    <section class="host-section">
      <h2>Host on this screen</h2>
      <button class="host-button" :disabled="busy" @click="create">Create room <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" /></svg></button>
    </section>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    </div>

    <nav v-if="!isTouch || $route.query.dev !== undefined" class="dev">
      <RouterLink to="/sensors">Sensor playground</RouterLink>
      <RouterLink to="/screen?mock=1">Mock screen</RouterLink>
    </nav>
  </main>
</template>

<style scoped>
.home {
  isolation: isolate;
  width: min(100%, 72rem);
  min-height: 100dvh;
  margin-inline: auto;
  padding: max(3rem, env(safe-area-inset-top)) max(1.5rem, env(safe-area-inset-right)) max(1.5rem, env(safe-area-inset-bottom)) max(1.5rem, env(safe-area-inset-left));
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 2rem 4rem;
  align-content: center;
  align-items: center;
}
.intro { padding-bottom: 0; min-width: 0; }
h1 { font-family: 'Barlow Condensed', sans-serif; font-style: italic; text-transform: uppercase; font-size: clamp(4rem, 8vw, 6rem); font-weight: 900; letter-spacing: -0.025em; line-height: 0.95; margin: 0 0 1.5rem; }
.brand-period { color: var(--orange); }
.lede { color: var(--muted); font-size: 1.125rem; line-height: 1.7; margin: 0; max-width: 35ch; text-wrap: pretty; }
.court-preview { max-width: 30rem; margin-top: 2rem; transform: rotate(-4deg); }
.court { display: block; width: 100%; overflow: visible; }
.court text { fill: #fff5dc; font: italic 900 22px 'Barlow Condensed', sans-serif; letter-spacing: 1px; }
.team-controls { display: flex; justify-content: space-around; color: var(--muted); font-size: 0.8rem; margin-top: 0.25rem; }
.court-ball { animation: opening-throw 900ms cubic-bezier(0.16, 1, 0.3, 1) both; }
@keyframes opening-throw { from { transform: translate(-60px, 40px); } to { transform: translate(0, 0); } }
.entry { padding: 2rem; background: var(--surface); border-radius: 12px; min-width: 0; }
.field { display: grid; gap: 0.65rem; margin-bottom: 2rem; font-size: 0.875rem; font-weight: 600; }
.field > span { display: flex; justify-content: space-between; gap: 1rem; }
.optional { color: var(--muted); font-weight: 400; }
h2 { font: italic 900 2.25rem/1.1 'Barlow Condensed', sans-serif; text-transform: uppercase; letter-spacing: 0; margin: 0 0 1rem; }
form { display: grid; gap: 0.85rem; }
input { width: 100%; min-width: 0; font: inherit; font-size: 1rem; padding: 0.85rem 1rem; border-radius: 8px; border: 1px solid var(--line); background: var(--bg); color: var(--text); }
input::placeholder { color: var(--muted); opacity: 1; }
input:hover { border-color: #6c778b; }
input:focus { outline: 2px solid var(--blue); outline-offset: 3px; }
.code { min-height: 4rem; font-size: clamp(1.1rem, 4vw, 1.45rem); font-weight: 650; letter-spacing: 0.17em; text-indent: 0.17em; text-transform: uppercase; text-align: center; font-variant-numeric: tabular-nums; }
.devices { display: grid; grid-template-columns: 1.3fr 1fr; gap: 0.5rem; }
.devices label { min-width: 0; display: flex; align-items: center; justify-content: center; gap: 0.5rem; min-height: 3rem; padding: 0.65rem 0.4rem; border: 1px solid var(--line); border-radius: 8px; color: var(--muted); font-size: 0.875rem; cursor: pointer; }
.devices label.on { background: #1e3046; border-color: var(--blue); color: var(--text); }
.devices label:hover { border-color: var(--blue); }
.devices input { width: 1rem; height: 1rem; margin: 0; accent-color: var(--blue); }
.devices label:focus-within { outline: 2px solid var(--blue); outline-offset: 3px; }
button { width: 100%; min-width: 0; min-height: 3.25rem; padding: 0.8rem 1rem; display: flex; align-items: center; justify-content: space-between; gap: 1rem; font: inherit; font-weight: 700; border: 0; border-radius: 8px; background: var(--orange); color: #101820; cursor: pointer; transition: background 160ms ease-out; }
button:hover:not(:disabled) { background: #ffae64; }
button:disabled { background: #2c394a; color: #a3b0c2; cursor: not-allowed; }
form > button { font: italic 900 1.5rem/1.2 'Barlow Condensed', sans-serif; text-transform: uppercase; letter-spacing: 0.02em; }
button svg { width: 22px; height: 22px; fill: none; stroke: currentColor; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
.host-section { margin-top: 1.75rem; padding-top: 1.5rem; border-top: 1px solid var(--line); }
.host-section h2 { font: inherit; font-size: 0.875rem; color: var(--muted); font-weight: 500; text-transform: none; }
.host-button { background: #213c56; color: #b8d8ff; border: 1px solid #4c7fb1; }
.host-button:hover:not(:disabled) { background: #263247; }
.error { margin: 1rem 0 0; color: var(--danger); line-height: 1.5; overflow-wrap: anywhere; }
.dev { grid-column: 1 / -1; display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 1.5rem; font-size: 0.8rem; }
.dev a { color: var(--muted); padding-block: 0.75rem; text-underline-offset: 4px; }
.dev a:hover { color: var(--text); }
@media (max-width: 760px) {
  .home { width: min(100%, 32rem); grid-template-columns: minmax(0, 1fr); gap: 1.75rem; padding-top: max(2rem, env(safe-area-inset-top)); }
  .intro { padding: 0; }
  h1 { margin-bottom: 1rem; }
  .lede { font-size: 1rem; }
  .court-preview { max-width: 13rem; margin: 1rem auto 0; }
  .entry { padding: 1.5rem; }
  .dev { justify-content: center; gap: 1.25rem; }
}
@media (max-width: 360px) { .home { padding-inline: 1rem; } .entry { padding: 1.1rem; } .devices { grid-template-columns: 1fr; } }
</style>
