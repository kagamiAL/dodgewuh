import { createRouter, createWebHistory, type RouteComponent } from 'vue-router'
import Home from './views/Home.vue'
import NotMerged from './views/NotMerged.vue'

// Tysen owns src/playground/**. Load it only if it exists so this route
// works before his branch merges, without stubbing files in his directory.
const playground = import.meta.glob<{ default: RouteComponent }>('./playground/SensorPlayground.vue')
const loadPlayground = playground['./playground/SensorPlayground.vue'] ?? (async () => ({ default: NotMerged }))

export const routes = [
  { path: '/', name: 'home', component: Home },
  { path: '/screen', name: 'screen', component: () => import('./views/Screen.vue') },
  { path: '/phone', name: 'phone', component: () => import('./views/PhoneShell.vue') },
  { path: '/sensors', name: 'sensors', component: loadPlayground },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
