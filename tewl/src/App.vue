<script setup lang="ts">
import { onMounted } from "vue";
import { useWallet } from "./composables/useWallet";
import { Button } from "@/components/ui/button";
import WalletDialog from "@/components/WalletDialog.vue";

const { wallet, isAnyWalletConnected, state, init, openWalletDialog, signOut } = useWallet();

onMounted(() => {
  init();
});

function truncateAddress(addr: string) {
  return addr ? `${addr.slice(0, 10)}...${addr.slice(-6)}` : "";
}
</script>

<template>
  <div class="min-h-screen bg-background">
    <!-- Header -->
    <header class="border-b">
      <div class="container mx-auto px-4 py-3 flex items-center justify-between">
        <div class="flex items-center gap-6">
          <router-link to="/" class="text-xl font-bold">TEWL</router-link>
          <nav class="flex gap-4">
            <router-link to="/" class="text-sm hover:text-primary">Dashboard</router-link>
            <router-link to="/providers" class="text-sm hover:text-primary">Providers</router-link>
            <router-link to="/provider" class="text-sm hover:text-primary">My Provider</router-link>
            <router-link to="/request/new" class="text-sm hover:text-primary">Create Request</router-link>
            <router-link to="/admin" class="text-sm hover:text-primary">Admin</router-link>
          </nav>
        </div>
        
        <div class="flex items-center gap-2">
          <template v-if="state.isLoading">
            <span class="text-sm text-muted-foreground">Loading...</span>
          </template>
          <template v-else-if="isAnyWalletConnected">
            <button @click="openWalletDialog" class="text-sm font-mono hover:text-primary">
              {{ truncateAddress(wallet.address!) }}
            </button>
            <button @click="signOut" class="text-sm text-destructive hover:underline">
              Disconnect
            </button>
          </template>
          <template v-else>
            <Button size="sm" @click="openWalletDialog">Connect Wallet</Button>
          </template>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <main class="container mx-auto px-4 py-6">
      <router-view />
    </main>

    <!-- Wallet Dialog -->
    <WalletDialog />
  </div>
</template>
