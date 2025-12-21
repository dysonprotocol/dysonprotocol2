<script setup lang="ts">
import { computed, ref } from "vue";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { useWallet } from "@/composables/useWallet";

const {
  walletDialogVisible,
  unlockedWallets,
  localCosmJsWallets,
  connectExtension,
  importNamedCosmJsWallet,
  connectNamedCosmJsWallet,
  generateMnemonic,
  signOut,
} = useWallet();

const loading = ref(false);
const keplrError = ref("");
const importError = ref("");
const mnemonic = ref("");
const walletName = ref("");
const password = ref("");

const hasKeplrWallet = computed(() => unlockedWallets.value.some((w) => w.type === "keplr"));
const keplrWallet = computed(() => unlockedWallets.value.find((w) => w.type === "keplr"));
const hasCosmJsWallet = computed(() => unlockedWallets.value.some((w) => w.type === "cosmjs"));
const cosmJsWallet = computed(() => unlockedWallets.value.find((w) => w.type === "cosmjs"));
const canImport = computed(() => walletName.value.trim() && mnemonic.value.trim() && password.value.trim());

async function handleConnectKeplr() {
  loading.value = true;
  keplrError.value = "";
  try {
    await connectExtension("keplr");
  } catch (err: any) {
    keplrError.value = err.message || "Failed to connect Keplr";
  } finally {
    loading.value = false;
  }
}

function handleDisconnect() {
  signOut();
}

async function handleImport() {
  loading.value = true;
  importError.value = "";
  try {
    await importNamedCosmJsWallet(walletName.value.trim(), mnemonic.value.trim(), password.value);
    mnemonic.value = "";
    walletName.value = "";
    password.value = "";
  } catch (err: any) {
    importError.value = err.message || "Import failed";
  } finally {
    loading.value = false;
  }
}

async function unlockLocal(w: { name: string }, pw: string) {
  if (!pw) return;
  loading.value = true;
  importError.value = "";
  try {
    await connectNamedCosmJsWallet(w.name, pw);
  } catch (err: any) {
    importError.value = err.message || "Unlock failed";
  } finally {
    loading.value = false;
  }
}

async function generate12() {
  mnemonic.value = await generateMnemonic(12);
}

async function generate24() {
  mnemonic.value = await generateMnemonic(24);
}

const unlockPasswords = ref<Record<string, string>>({});
</script>

<template>
  <Dialog v-model:open="walletDialogVisible">
    <DialogContent class="max-w-sm">
      <DialogHeader>
        <DialogTitle>Connect Wallet</DialogTitle>
      </DialogHeader>

      <div class="space-y-4">
        <!-- Connected Keplr -->
        <section v-if="hasKeplrWallet">
          <div class="border rounded-lg p-3">
            <div class="flex items-center justify-between">
              <span class="font-medium">{{ keplrWallet?.name }}</span>
              <Button variant="outline" size="sm" :disabled="loading" @click="handleDisconnect">
                Disconnect
              </Button>
            </div>
            <div class="mt-1 font-mono text-xs text-muted-foreground break-all">
              {{ keplrWallet?.address }}
            </div>
          </div>
        </section>

        <!-- Connected CosmJS -->
        <section v-else-if="hasCosmJsWallet">
          <div class="border rounded-lg p-3">
            <div class="flex items-center justify-between">
              <span class="font-medium">{{ cosmJsWallet?.name }}</span>
              <Button variant="outline" size="sm" :disabled="loading" @click="handleDisconnect">
                Disconnect
              </Button>
            </div>
            <div class="mt-1 font-mono text-xs text-muted-foreground break-all">
              {{ cosmJsWallet?.address }}
            </div>
          </div>
        </section>

        <!-- Keplr Button -->
        <Button v-else class="w-full" :disabled="loading" @click="handleConnectKeplr">
          {{ loading ? "Connecting..." : "Connect Keplr" }}
        </Button>

        <div v-if="keplrError" class="text-destructive text-sm">{{ keplrError }}</div>

        <!-- Divider -->
        <div v-if="!hasKeplrWallet && !hasCosmJsWallet" class="relative">
          <div class="absolute inset-0 flex items-center"><span class="w-full border-t" /></div>
          <div class="relative flex justify-center text-xs"><span class="bg-background px-2 text-muted-foreground">or import seed</span></div>
        </div>

        <!-- Import Form -->
        <form v-if="!hasKeplrWallet && !hasCosmJsWallet" class="space-y-3" @submit.prevent="handleImport">
          <div class="space-y-2">
            <Label>Wallet Name</Label>
            <Input v-model="walletName" placeholder="My Wallet" />
          </div>
          <div class="space-y-2">
            <Label>Seed Phrase</Label>
            <Textarea v-model="mnemonic" placeholder="Enter 12 or 24 word seed phrase..." rows="3" class="text-sm" />
          </div>
          <div class="flex gap-2">
            <Button type="button" variant="outline" size="sm" :disabled="loading" @click="generate12">12 words</Button>
            <Button type="button" variant="outline" size="sm" :disabled="loading" @click="generate24">24 words</Button>
          </div>
          <div class="space-y-2">
            <Label>Password</Label>
            <Input v-model="password" type="password" placeholder="Encrypt wallet locally" />
          </div>
          <div v-if="importError" class="text-destructive text-sm">{{ importError }}</div>
          <Button type="submit" class="w-full" :disabled="!canImport || loading">
            {{ loading ? "Importing..." : "Import Wallet" }}
          </Button>
        </form>

        <!-- Saved Local Wallets -->
        <div v-if="localCosmJsWallets.length > 0 && !hasKeplrWallet && !hasCosmJsWallet" class="space-y-2">
          <div class="text-sm text-muted-foreground">Saved wallets:</div>
          <div v-for="w in localCosmJsWallets" :key="w.name" class="flex items-center justify-between border rounded-lg p-2 gap-2">
            <div class="min-w-0 flex-1">
              <div class="font-medium text-sm truncate">{{ w.name }}</div>
              <div class="font-mono text-xs text-muted-foreground">{{ w.address.slice(0, 12) }}...</div>
            </div>
            <div class="flex gap-2 items-center">
              <Input v-model="unlockPasswords[w.name]" type="password" placeholder="Password" class="w-24 h-8" @keyup.enter="unlockLocal(w, unlockPasswords[w.name])" />
              <Button size="sm" @click="unlockLocal(w, unlockPasswords[w.name])">Unlock</Button>
            </div>
          </div>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>

