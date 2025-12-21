<template>
  <Dialog v-model:open="modelOpen">
    <DialogContent class="max-w-sm">
      <DialogHeader>
        <DialogTitle>Connect Wallet</DialogTitle>
      </DialogHeader>

      <div class="space-y-4">
        <!-- Keplr section -->
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

        <Button
          v-else
          class="w-full"
          :disabled="loading"
          @click="handleConnectKeplr"
        >
          {{ loading ? 'Connecting...' : 'Connect Keplr' }}
        </Button>

        <div v-if="keplrError" class="text-destructive text-sm">{{ keplrError }}</div>

        <!-- Local wallet section -->
        <div class="relative">
          <div class="absolute inset-0 flex items-center"><span class="w-full border-t" /></div>
          <div class="relative flex justify-center text-xs"><span class="bg-background px-2 text-muted-foreground">or import seed</span></div>
        </div>

        <form v-if="!hasKeplrWallet" class="space-y-3" @submit.prevent="handleImport">
          <Input v-model="walletName" placeholder="Wallet name" />
          <textarea
            v-model="mnemonic"
            placeholder="Enter 12 or 24 word seed phrase..."
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none h-20"
          />
          <div class="flex gap-2">
            <Button type="button" variant="outline" size="sm" :disabled="loading" @click="generate12">12 words</Button>
            <Button type="button" variant="outline" size="sm" :disabled="loading" @click="generate24">24 words</Button>
          </div>
          <Input v-model="password" type="password" placeholder="Password to encrypt" />
          <div v-if="importError" class="text-destructive text-sm">{{ importError }}</div>
          <Button type="submit" class="w-full" :disabled="!canImport || loading">
            {{ loading ? 'Importing...' : 'Import Wallet' }}
          </Button>
        </form>

        <!-- Existing local wallets -->
        <div v-if="localCosmJsWallets.length > 0 && !hasKeplrWallet" class="space-y-2">
          <div class="text-sm text-muted-foreground">Saved wallets:</div>
          <div
            v-for="w in localCosmJsWallets"
            :key="w.name"
            class="flex items-center justify-between border rounded-lg p-2"
          >
            <div>
              <div class="font-medium text-sm">{{ w.name }}</div>
              <div class="font-mono text-xs text-muted-foreground">{{ w.address.slice(0, 12) }}...</div>
            </div>
            <div class="flex gap-2">
              <Input
                :id="`pw-${w.name}`"
                type="password"
                placeholder="Password"
                class="w-24 h-8"
                @keyup.enter="unlockLocal(w)"
              />
              <Button size="sm" @click="unlockLocal(w)">Unlock</Button>
            </div>
          </div>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useWallet } from '@/composables/useWallet'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ 'update:visible': [value: boolean] }>()

const modelOpen = computed({
  get: () => props.visible,
  set: (v) => emit('update:visible', v),
})

const {
  unlockedWallets,
  localCosmJsWallets,
  connectExtension,
  importNamedCosmJsWallet,
  connectNamedCosmJsWallet,
  generateMnemonic,
  signOut,
} = useWallet()

const loading = ref(false)
const keplrError = ref('')
const importError = ref('')
const mnemonic = ref('')
const walletName = ref('')
const password = ref('')

const hasKeplrWallet = computed(() => unlockedWallets.value.some((w) => w.type === 'keplr'))
const keplrWallet = computed(() => unlockedWallets.value.find((w) => w.type === 'keplr'))
const canImport = computed(() => walletName.value.trim() && mnemonic.value.trim() && password.value.trim())

async function handleConnectKeplr() {
  loading.value = true
  keplrError.value = ''
  try {
    await connectExtension('keplr')
    modelOpen.value = false
  } catch (err: any) {
    keplrError.value = err.message || 'Failed to connect Keplr'
  } finally {
    loading.value = false
  }
}

function handleDisconnect() {
  signOut()
}

async function handleImport() {
  loading.value = true
  importError.value = ''
  try {
    await importNamedCosmJsWallet(walletName.value.trim(), mnemonic.value.trim(), password.value)
    mnemonic.value = ''
    walletName.value = ''
    password.value = ''
    modelOpen.value = false
  } catch (err: any) {
    importError.value = err.message || 'Import failed'
  } finally {
    loading.value = false
  }
}

async function unlockLocal(w: { name: string }) {
  const input = document.getElementById(`pw-${w.name}`) as HTMLInputElement
  if (!input?.value) return
  loading.value = true
  importError.value = ''
  try {
    await connectNamedCosmJsWallet(w.name, input.value)
    modelOpen.value = false
  } catch (err: any) {
    importError.value = err.message || 'Unlock failed'
  } finally {
    loading.value = false
  }
}

async function generate12() {
  mnemonic.value = await generateMnemonic(12)
}

async function generate24() {
  mnemonic.value = await generateMnemonic(24)
}
</script>
