<script setup lang="ts">
import { ref } from 'vue'
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
    await router.push(to)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
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
    <h1>dodgewuh</h1>
    <p class="lede">Four phones, two characters. One teammate moves, the other aims and throws.</p>

    <label class="field">
      Your name
      <input v-model="name" maxlength="24" autocomplete="nickname" placeholder="Optional" />
    </label>

    <section class="card">
      <h2>Join a room</h2>
      <form @submit.prevent="join">
        <input
          v-model="code"
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
        <button type="submit" :disabled="busy || code.trim().length !== 6">Join</button>
      </form>
    </section>

    <section class="card">
      <h2>Host on this screen</h2>
      <button :disabled="busy" @click="create">Create room</button>
    </section>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <nav v-if="!isTouch || $route.query.dev !== undefined" class="dev">
      <RouterLink to="/sensors">Sensor playground</RouterLink>
      <RouterLink to="/screen?mock=1">Mock screen</RouterLink>
    </nav>
  </main>
</template>

<style scoped>
.home {
  width: 100%;
  max-width: 28rem;
  margin: 0 auto;
  /* Respect notches/rounded corners in landscape (index.html sets viewport-fit=cover). */
  padding: 2rem max(1rem, env(safe-area-inset-right)) max(2rem, env(safe-area-inset-bottom))
    max(1rem, env(safe-area-inset-left));
  box-sizing: border-box;
  overflow-wrap: break-word;
}
h1 {
  margin: 0 0 0.25rem;
  font-size: clamp(1.75rem, 9vw, 2.5rem);
}
.lede {
  color: #aaa;
  margin-top: 0;
}
.field {
  display: grid;
  gap: 0.35rem;
  margin: 1.5rem 0 1rem;
}
.card {
  margin: 1rem 0;
  padding: 1rem;
  border: 1px solid #333;
  border-radius: 12px;
}
.card h2 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
}
form {
  display: grid;
  gap: 0.75rem;
}
/* Grid/flex children default to min-width:auto, so an input's intrinsic size
   (default size=20, plus the code field's tracking) would push past the card. */
.field,
form,
.devices,
.card {
  min-width: 0;
}
input {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  font: inherit;
  /* <16px makes iOS Safari zoom the page on focus. */
  font-size: max(1rem, 16px);
  padding: 0.7rem;
  border-radius: 8px;
  border: 1px solid #444;
  background: #1b1b1b;
  color: inherit;
}
.code {
  font-size: clamp(1.1rem, 6vw, 1.5rem);
  letter-spacing: clamp(0.12em, 1.5vw, 0.3em);
  /* The trailing letter-space would otherwise push the text off-centre. */
  text-indent: clamp(0.12em, 1.5vw, 0.3em);
  text-transform: uppercase;
  text-align: center;
}
.devices {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr));
  gap: 0.5rem;
}
.devices label {
  min-width: 0;
  padding: 0.7rem;
  border: 1px solid #444;
  border-radius: 8px;
  text-align: center;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.devices label.on {
  border-color: #8cf;
  color: #8cf;
}
.devices input {
  position: absolute;
  opacity: 0;
  width: 0;
  pointer-events: none;
}
/* Keyboard focus is invisible once the radio itself is hidden. */
.devices label:focus-within {
  outline: 2px solid #8cf;
  outline-offset: 2px;
}
button {
  width: 100%;
  min-width: 0;
  min-height: 3rem;
  font: inherit;
  font-weight: 700;
  border: 0;
  border-radius: 10px;
  background: #8cf;
  color: #000;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
button:disabled {
  opacity: 0.4;
  cursor: default;
}
.error {
  color: #f77;
}
.dev {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-top: 2rem;
  font-size: 0.85rem;
}
.dev a {
  color: #8cf;
  /* Comfortable tap target without changing the layout much. */
  padding: 0.35rem 0;
}
@media (max-width: 22rem) {
  .home {
    padding-top: 1.25rem;
  }
  .card {
    padding: 0.75rem;
  }
}
</style>
