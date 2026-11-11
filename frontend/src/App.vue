<template>
  <router-view v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>

<script setup>
import { onMounted } from 'vue'

onMounted(() => {
  const theme = localStorage.getItem('theme') || 'light'
  document.documentElement.classList.toggle('dark', theme === 'dark')
})
</script>
