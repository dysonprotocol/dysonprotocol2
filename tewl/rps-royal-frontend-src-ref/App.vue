<script setup lang="ts">
import { useWallet } from '@/composables/useWallet'
import WalletDialog from '@/components/shared/WalletDialog.vue'
import GlobalTransactionDialog from '@/components/shared/GlobalTransactionDialog.vue'
import { Toaster } from 'vue-sonner'

const { walletDialogVisible } = useWallet()
</script>

<template>
  <router-view />
  <WalletDialog v-model:visible="walletDialogVisible" />
  <GlobalTransactionDialog />
  <Toaster position="top-center" rich-colors />
</template>



