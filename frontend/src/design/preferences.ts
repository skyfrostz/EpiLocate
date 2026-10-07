import { computed, ref } from 'vue'
export type DisplayTheme = 'light' | 'dark' | 'system'
export type DisplayDensity = 'compact' | 'standard' | 'comfortable'
const key = 'epilocate-display-v1'
function read() { try { return JSON.parse(localStorage.getItem(key) || '{}') } catch { return {} } }
const saved = read()
export const displayTheme = ref<DisplayTheme>(['light', 'dark', 'system'].includes(saved?.theme) ? saved.theme : 'system')
export const displayDensity = ref<DisplayDensity>(['compact', 'standard', 'comfortable'].includes(saved?.density) ? saved.density : 'standard')
export const reducedMotion = ref(saved?.reducedMotion === true)
const systemDark = ref(false)
export const resolvedTheme = computed(() => displayTheme.value === 'system' ? systemDark.value ? 'dark' : 'light' : displayTheme.value)
export function applyDisplay() {
  document.documentElement.dataset.theme = resolvedTheme.value
  document.documentElement.dataset.density = displayDensity.value
  document.documentElement.dataset.reducedMotion = String(reducedMotion.value)
}
export function saveDisplay() {
  try { localStorage.setItem(key, JSON.stringify({ theme: displayTheme.value, density: displayDensity.value, reducedMotion: reducedMotion.value })) } catch { /* In-memory preferences still work. */ }
  applyDisplay()
}
export function initializeDisplay() {
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const change = () => { systemDark.value = media.matches; applyDisplay() }
  media.addEventListener('change', change); change()
  return () => media.removeEventListener('change', change)
}
