/// <reference types="vite/client" />

// Lets editors without the Vue extension resolve .vue imports.
// vue-tsc and the Vue (Official) extension use the real component types instead.
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}
