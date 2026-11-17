<script setup>
defineProps({ name: { type: String, default: 'video' } })
const paths = {
  video: 'M15 9l5-3v12l-5-3M4 5h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z',
  chart: 'M4 3v17h17M8 15v-4m5 4V7m5 8v-5',
  activity: 'M3 12h4l3-8 4 16 3-8h4',
  play: 'M9 5l11 7-11 7V5Z',
  upload: 'M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5',
  plus: 'M12 5v14M5 12h14',
  download: 'M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4',
  clock: 'M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
  arrow: 'M5 12h14m-5-5 5 5-5 5',
  refresh: 'M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 2M4 16l2 2a7 7 0 0 0 12-1',
  grid: 'M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm11 0h7v7h-7v-7Z',
}
</script>
<template><svg class="studio-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.video" /></svg></template>
