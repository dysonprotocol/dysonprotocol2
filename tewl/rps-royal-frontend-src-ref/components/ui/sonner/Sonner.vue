<script lang="ts" setup>
import type { ToasterProps } from 'vue-sonner'
import { Toaster as ShadToaster } from 'vue-sonner'

const props = defineProps<ToasterProps>()
defineOptions({ name: 'UiSonnerToaster' })
</script>

<template>
  <ShadToaster
    class="toaster group"
    v-bind="props"
    position="bottom-right"
    :expand="true"
    :visible-toasts="5"
    rich-colors
    close-button
  />
</template>
