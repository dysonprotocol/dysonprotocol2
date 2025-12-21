<template>
  <div class="relative min-w-0 overflow-hidden">
    <Dialog v-model:open="isOpen">
      <DialogTrigger asChild>
        <Button
          type="button"
          :class="['min-w-0', 'overflow-hidden', buttonClass]"
          data-testid="wallet-selector-open"
        >
          <span class="ml-1 flex-1 min-w-0 truncate">{{ selectedLabel }}</span>
          <ChevronUpIcon v-if="isOpen" class="size-4 opacity-70" />
          <ChevronDownIcon v-else class="size-4 opacity-70" />
        </Button>
      </DialogTrigger>

      <DialogContent>
        <div data-testid="wallet-selector-modal">
          <DialogHeader>
            <DialogTitle>Select wallet</DialogTitle>
          </DialogHeader>

          <div
            v-if="selectedAuthz && selectedAuthz.notes"
            class="mt-2 text-xs opacity-80 break-all"
          >
            Note: {{ selectedAuthz.notes }}
          </div>
          <ul class="mt-4">
            <li v-if="groupedOptions.length === 0" class="px-4 py-2 text-sm opacity-70">
              No wallets available. Enable Keplr or add and unlock a JS wallet in the sidebar.
            </li>
            <li v-for="group in groupedOptions" :key="group.wallet.address" class="my-1">
              <div
                class="w-full text-left p-4 text-sm rounded-md border border-primary/10"
                :class="{
                  'cursor-not-allowed': !group.wallet.isUnlocked || !group.directAllowed,
                  'hover:cursor-pointer border-primary/40 hover:bg-primary/10':
                    group.wallet.isUnlocked && group.directAllowed,
                  'bg-primary/10': isDirectSelected(group.wallet.address),
                }"
                :data-testid="`wallet-item-${group.wallet.name}`"
                @click="
                  group.wallet.isUnlocked &&
                  group.directAllowed &&
                  selectDirect(group.wallet.address)
                "
              >
                <div
                  class="flex items-start justify-between"
                  :class="{ 'opacity-50': !group.wallet.isUnlocked || !group.directAllowed }"
                >
                  <p
                    :class="
                      isDirectSelected(group.wallet.address) ? 'font-semibold' : 'font-normal'
                    "
                  >
                    {{ group.wallet.name }}
                    <span class="text-xs text-base-content/60">({{ group.wallet.type }})</span>
                  </p>
                  <span v-if="isDirectSelected(group.wallet.address)" class="text-primary">
                    <CheckIcon class="size-5" />
                  </span>
                </div>
                <div class="mt-2 font-mono text-xs break-all">
                  {{ group.wallet.address }}
                </div>

                <div v-if="group.wallet.isUnlocked && group.authzOptions.length > 0" class="mt-3">
                  <div class="text-xs text-base-content/60 mb-1">Via Authz</div>
                  <div class="space-y-1">
                    <Button
                      v-for="(auth, idx) in group.authzOptions"
                      :key="auth.granterAddress + ':' + idx"
                      type="button"
                      variant="outline"
                      class="w-full justify-start border-primary/60 hover:bg-primary/10 h-auto"
                      :class="{
                        'bg-primary/10': isAuthzSelected(group.wallet.address, auth),
                      }"
                      @click.stop="selectAuthz(group.wallet, auth)"
                    >
                      <div class="w-full">
                        <div class="flex items-center justify-between">
                          <div>
                            <span class="font-medium">{{ short(auth.granterAddress) }}</span>
                            <span class="opacity-70"> via Authz</span>
                            <span class="opacity-70"> (signed by {{ group.wallet.name }})</span>
                          </div>
                          <span
                            v-if="isAuthzSelected(group.wallet.address, auth)"
                            class="text-primary"
                          >
                            <CheckIcon class="size-5" />
                          </span>
                        </div>
                        <div class="text-xs opacity-70 mt-1 flex items-center gap-2">
                          <span>{{ auth.notes }}</span>
                          <span v-if="auth.expiration" :title="auth.expiration"
                            >exp: {{ shortTs(auth.expiration) }}</span
                          >
                        </div>
                      </div>
                    </Button>
                  </div>
                </div>
              </div>
            </li>
          </ul>
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, watch } from 'vue'
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from '@heroicons/vue/20/solid'
import { useWallet } from '@/composables/useWallet'
import { useAxiosRepo } from '@pinia-orm/axios'
import { useRepo } from 'pinia-orm'
import { Grant } from '@/orm/models/authz/Grant'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

const props = defineProps({
  modelValue: { type: String, default: '' },
  allowedAddresses: { type: Array, default: null },
  showLocked: { type: Boolean, default: true },
  defaultAddress: { type: String, default: '' },
  defaultGrantee: { type: String, default: '' },
  buttonClass: { type: String, default: '' },
  msgTypeFilter: { type: Function, default: null },
})
const emit = defineEmits([
  'update:modelValue',
  'update:executorAddress',
  'update:granteeAddress',
  'update:isAuthz',
  'update:authzNotes',
  'update:selectedGrant',
])
const { unlockedWallets, localCosmJsWallets, loadDenomMetadata, chainId } = useWallet()

onMounted(async () => {
  try {
    await loadDenomMetadata()
  } catch {
    // ignore load errors here; component still functions
  }
})

const isOpen = ref(false)

const allowedSet = computed(() => (props.allowedAddresses ? new Set(props.allowedAddresses) : null))

function truncate(a) {
  if (!a) return ''
  return a.length <= 12 ? a : `${a.slice(0, 6)}...${a.slice(-6)}`
}

const all = computed(() => {
  const unlocked = unlockedWallets.value.map((w) => ({
    ...w,
    isUnlocked: true,
  }))
  const lockedBase = props.showLocked
    ? localCosmJsWallets.value.filter(
        (w) => !unlockedWallets.value.some((u) => u.address === w.address)
      )
    : []
  const locked = lockedBase.map((w) => ({
    ...w,
    isUnlocked: false,
    type: 'cosmjs',
  }))
  return [...unlocked, ...locked]
})

// AUTHZ fetching and filtering
function short(a) {
  if (!a) return ''
  return a.length <= 13 ? a : `${a.slice(0, 10)}...${a.slice(-5)}`
}

function shortTs(ts) {
  try {
    const d = new Date(ts)
    return isNaN(d.getTime()) ? ts : d.toISOString().slice(0, 19).replace('T', ' ')
  } catch {
    return ts
  }
}

function isExpired(expiration) {
  if (!expiration) return false
  return new Date(expiration).getTime() <= Date.now()
}

function applyFilter(grants, filter) {
  if (!grants || grants.length === 0) return []
  const fn = filter
  if (!fn) return []
  return grants
    .filter((g) => !isExpired(g.expiration))
    .map((g) => ({ g, res: fn(g) }))
    .filter((x) => x.res && x.res.valid)
    .map((x) => ({ grant: x.g, notes: x.res.notes || '' }))
}

const filteredByGrantee = ref({})

async function refreshAuthz() {
  const filter = props.msgTypeFilter
  const unlocked = unlockedWallets.value.map((w) => w.address)
  const entries = {}
  const api = useAxiosRepo(Grant).api()
  const repo = useRepo(Grant)
  await Promise.allSettled(unlocked.map((addr) => api.fetchByGrantee(addr)))
  unlocked.forEach((addr) => {
    const grants = repo.where('grantee', addr).get()
    const filtered = applyFilter(grants, filter)
    entries[addr] = filtered.map((f) => ({
      isAuthz: true,
      granterAddress: f.grant.granter,
      granteeAddress: f.grant.grantee,
      notes: f.notes,
      expiration: f.grant.expiration || null,
      grant: f.grant,
    }))
  })
  filteredByGrantee.value = entries
}

// Watch dependencies and refresh (no caching across sessions)
onMounted(() => {
  if (props.msgTypeFilter) refreshAuthz()
})

watch(
  () => [
    unlockedWallets.value.map((w) => w.address).join(','),
    // removed restUrl dependency
    chainId.value,
    props.msgTypeFilter,
  ],
  () => {
    if (props.msgTypeFilter) refreshAuthz()
  }
)

const groupedOptions = computed(() => {
  const groups = all.value.map((w) => {
    const directAllowed = allowedSet.value ? allowedSet.value.has(w.address) : true
    const rawAuthz = filteredByGrantee.value[w.address] || []
    const authzOptions = rawAuthz.filter((a) =>
      allowedSet.value ? allowedSet.value.has(a.granterAddress) : true
    )
    return { wallet: w, directAllowed, authzOptions }
  })
  return groups
})

// Prefer Authz when both defaults are provided; fall back to direct if none selected
function ensureDefaultSelection() {
  // Try Authz first
  if (props.defaultAddress && props.defaultGrantee) {
    const groups = groupedOptions.value
    const signerGroup = groups.find(
      (g) => g.wallet.isUnlocked && g.wallet.address === props.defaultGrantee
    )
    const auth = signerGroup?.authzOptions.find((a) => a.granterAddress === props.defaultAddress)
    if (signerGroup && auth) {
      const already =
        !!selectedAuthz.value &&
        selectedAuthz.value.granter === auth.granterAddress &&
        selectedAuthz.value.grantee === signerGroup.wallet.address
      if (!already) selectAuthz(signerGroup.wallet, auth)
      return
    }
  }
  // Then direct only if no explicit selection
  if (!props.modelValue && props.defaultAddress) {
    const canDefault = groupedOptions.value.some(
      (g) => g.wallet.isUnlocked && g.wallet.address === props.defaultAddress && g.directAllowed
    )
    if (canDefault) emit('update:modelValue', props.defaultAddress)
  }
}

// Run on mount and when inputs change
onMounted(() => {
  ensureDefaultSelection()
})

watch(
  () => [props.defaultAddress, props.defaultGrantee, props.modelValue],
  () => ensureDefaultSelection()
)

watch(groupedOptions, () => ensureDefaultSelection())

// Track selected authz locally for label and checks
const selectedAuthz = ref(null)

// Initialize executor addresses when modelValue is already set (e.g., from persistence)
function initializeFromModelValue() {
  if (!props.modelValue) return
  
  // Check if this is an authz selection (would need both granter and grantee)
  // For now, assume direct selection if modelValue is set but no selectedAuthz
  if (!selectedAuthz.value) {
    const group = groupedOptions.value.find((g) => g.wallet.address === props.modelValue)
    if (group?.wallet.isUnlocked && group.directAllowed) {
      // Emit addresses without opening modal or changing modelValue
      emit('update:executorAddress', props.modelValue)
      emit('update:granteeAddress', null)
      emit('update:isAuthz', false)
      emit('update:authzNotes', '')
      emit('update:selectedGrant', null)
    }
  }
}

// Initialize on mount and when modelValue or groupedOptions change
onMounted(() => initializeFromModelValue())
watch(() => props.modelValue, initializeFromModelValue)
watch(groupedOptions, initializeFromModelValue)

const selectedLabel = computed(() => {
  if (selectedAuthz.value) {
    const signer = unlockedWallets.value.find((u) => u.address === selectedAuthz.value.grantee)
    const signerName = signer?.name || truncate(selectedAuthz.value.grantee)
    return `${short(selectedAuthz.value.granter)} via Authz (signed by ${signerName})`
  }
  const g = groupedOptions.value.find((x) => x.wallet.address === props.modelValue)
  if (g) return `${g.wallet.name}`
  return props.modelValue ? truncate(props.modelValue) : 'Select wallet'
})

// removed unused onUpdate handler

function closeModal() {
  isOpen.value = false
}

function selectDirect(address) {
  emit('update:modelValue', address)
  emit('update:executorAddress', address)
  emit('update:granteeAddress', null)
  emit('update:isAuthz', false)
  emit('update:authzNotes', '')
  emit('update:selectedGrant', null)
  selectedAuthz.value = null
  closeModal()
}

function selectAuthz(wallet, auth) {
  emit('update:modelValue', auth.granterAddress)
  emit('update:executorAddress', auth.granterAddress)
  emit('update:granteeAddress', wallet.address)
  emit('update:isAuthz', true)
  emit('update:authzNotes', auth.notes || '')
  emit('update:selectedGrant', auth.grant || null)
  selectedAuthz.value = {
    granter: auth.granterAddress,
    grantee: wallet.address,
    notes: auth.notes || '',
  }
  closeModal()
}

function isDirectSelected(address) {
  return !selectedAuthz.value && props.modelValue === address
}

function isAuthzSelected(granteeAddress, auth) {
  return (
    !!selectedAuthz.value &&
    selectedAuthz.value.granter === auth.granterAddress &&
    selectedAuthz.value.grantee === granteeAddress
  )
}

// copy removed; AddressDisplay handles presentation

// no-op: shadcn Dialog handled via v-model:open
</script>
