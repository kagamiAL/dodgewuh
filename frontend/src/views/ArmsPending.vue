<script setup lang="ts">
// Stand-in until controllers/arms/ArmsController.vue (Morteza) lands; PhoneShell switches
// to it automatically. Sends no gameplay input. In dev builds only, it can report itself
// calibrated so a real phone can occupy an Arms seat during the Legs vertical slice.
import { onBeforeUnmount, ref } from 'vue'
import type { RoleComponentProps } from '@/phone/roleComponent'
import type { Permission } from '@/contracts/pending'

defineProps<RoleComponentProps>()
const emit = defineEmits<{ calibrated: [value: boolean]; availability: [value: Permission] }>()

const dev = import.meta.env.DEV
const standIn = ref(false)

function toggle(): void {
  standIn.value = !standIn.value
  emit('availability', standIn.value ? 'granted' : 'unknown')
  emit('calibrated', standIn.value)
}

onBeforeUnmount(() => {
  if (standIn.value) emit('calibrated', false)
})
</script>

<template>
  <section class="arms">
    <h1>Arms</h1>
    <p>The Arms controller is not merged yet. This seat cannot aim or throw.</p>
    <button v-if="dev" :class="{ on: standIn }" @click="toggle">
      {{ standIn ? 'Dev stand-in: calibrated' : 'Dev only: act as calibrated stand-in' }}
    </button>
  </section>
</template>

<style scoped>
.arms {
  padding: 1rem;
}
p {
  color: #aaa;
}
button {
  width: 100%;
  min-height: 3rem;
  font: inherit;
  border: 1px dashed #fb4;
  border-radius: 10px;
  background: transparent;
  color: #fb4;
}
button.on {
  background: #fb4;
  color: #000;
}
</style>
