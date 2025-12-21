<script setup lang="ts">
import { ref, computed } from "vue";
import { VisXYContainer, VisLine, VisArea, VisScatter } from "@unovis/vue";
import { toast } from "vue-sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ChartContainer,
  ChartTooltip,
  ChartCrosshair,
  ChartTooltipContent,
  componentToString,
  type ChartConfig,
} from "@/components/ui/chart";
import { useEnergyMarket, useEnergySwap } from "@/composables/useEnergyMarket";

const props = defineProps<{
  energyBalance: number;
  dysBalance: string;
}>();

// Amount input
const amount = ref<number>(100);

// Real trade data from whaleswap API (last 100 trades)
const { priceHistory, currentPrice, priceChange, isUp, isLoading } =
  useEnergyMarket(10);

// Swap functionality
const {
  isPending,
  error: swapError,
  isPoolLoading,
  getBuyQuote,
  getSellQuote,
  buyEnergy,
  sellEnergy,
} = useEnergySwap();

// Chart config for tooltip theming
const chartConfig: ChartConfig = {
  price: {
    label: "⚡/DYS",
    color: "#ef4444",
  },
};

// Normalize prices to 0-1 range with padding for chart display
const normalizedData = computed(() => {
  const history = priceHistory.value;
  if (history.length === 0) return [];

  const prices = history.map((p) => p.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min;

  return history.map((p, i) => ({
    idx: i,
    y: range > 0 ? 0.1 + ((p.price - min) / range) * 0.8 : 0.5,
    // Format price for tooltip display
    price: `${(p.price / 1_000_000).toFixed(6)} DYS`,
  }));
});

// Chart accessors for normalized data
const x = (d: { idx: number }) => d.idx;
const y = (d: { y: number }) => d.y;

// Line color based on trend
const lineColor = computed(() => (isUp.value ? "#22c55e" : "#ef4444"));

// Cost calculation using pool quote
const buyCost = computed(() => {
  const quote = getBuyQuote(amount.value);
  if (!quote) return "—";
  // Convert udys to DYS (6 decimals)
  return (Number(quote) / 1_000_000).toFixed(4);
});

// Sell quote for display
const sellReturn = computed(() => {
  const quote = getSellQuote(amount.value);
  if (!quote) return "—";
  return (Number(quote) / 1_000_000).toFixed(4);
});

// Can afford checks
const canBuy = computed(() => {
  if (isPending.value || isPoolLoading.value) return false;
  const quote = getBuyQuote(amount.value);
  if (!quote) return false;
  // dysBalance is in DYS, quote is in udys
  const dysBalanceUdys = parseFloat(props.dysBalance) * 1_000_000;
  return dysBalanceUdys >= Number(quote);
});

const canSell = computed(() => {
  if (isPending.value || isPoolLoading.value) return false;
  if (props.energyBalance < amount.value) return false;
  return !!getSellQuote(amount.value);
});

// Disabled reasons
const buyDisabledReason = computed(() => {
  if (isPending.value) return "Transaction pending...";
  if (isPoolLoading.value) return "Loading...";
  const quote = getBuyQuote(amount.value);
  if (!quote) return "Exceeds pool liquidity";
  const dysBalanceUdys = parseFloat(props.dysBalance) * 1_000_000;
  if (dysBalanceUdys < Number(quote)) return `Need ${buyCost.value} DYS`;
  return null;
});

const sellDisabledReason = computed(() => {
  if (isPending.value) return "Transaction pending...";
  if (isPoolLoading.value) return "Loading...";
  if (props.energyBalance < amount.value)
    return `Need ${amount.value - props.energyBalance}⚡ more`;
  const quote = getSellQuote(amount.value);
  if (!quote) return "Exceeds pool liquidity";
  return null;
});

async function handleBuy() {
  if (!canBuy.value) return;
  try {
    await buyEnergy(amount.value);
    toast.success(`Bought ${amount.value}⚡ energy`);
  } catch (err: any) {
    toast.error(`Buy failed: ${err.message || "Unknown error"}`);
  }
}

async function handleSell() {
  if (!canSell.value) return;
  try {
    await sellEnergy(amount.value);
    toast.success(`Sold ${amount.value}⚡ energy`);
  } catch (err: any) {
    toast.error(`Sell failed: ${err.message || "Unknown error"}`);
  }
}

// Format price for display (udys → DYS)
const displayPrice = computed(() => {
  const price = currentPrice.value;
  if (price === null) return "—";
  // Convert udys to DYS (6 decimals)
  return (price / 1_000_000).toFixed(6);
});
</script>

<template>
  <div class="space-y-3">
    <div
      class="text-xs font-semibold text-muted-foreground uppercase tracking-wider"
    >
      Energy Market
    </div>

    <!-- Price Chart (no grid, no labels - just the line) -->
    <div class="aspect-[2/1] w-full rounded bg-secondary/30 overflow-hidden">
      <template v-if="isLoading">
        <div
          class="h-full flex items-center justify-center text-muted-foreground text-xs"
        >
          Loading...
        </div>
      </template>
      <template v-else-if="normalizedData.length > 0">
        <ChartContainer :config="chartConfig" class="h-full w-full">
          <VisXYContainer :data="normalizedData">
            <VisArea :x="x" :y="y" :color="lineColor" :opacity="0.15" />
            <VisLine :x="x" :y="y" :color="lineColor" :lineWidth="1.5" />
            <VisScatter :x="x" :y="y" :color="lineColor" :size="5" />
            <ChartTooltip />
            <ChartCrosshair
              :template="
                componentToString(chartConfig, ChartTooltipContent, {
                  hideIndicator: true,
                  hideLabel: true,
                })
              "
              :color="lineColor"
            />
          </VisXYContainer>
        </ChartContainer>
      </template>
      <template v-else>
        <div
          class="h-full flex items-center justify-center text-muted-foreground text-xs"
        >
          No trades yet
        </div>
      </template>
    </div>

    <!-- Price Stats -->
    <div class="grid grid-cols-2 gap-2">
      <div class="bg-secondary/50 rounded p-2">
        <div class="text-[10px] text-muted-foreground uppercase">Price</div>
        <div class="font-mono font-bold">{{ displayPrice }} DYS</div>
      </div>
      <div class="bg-secondary/50 rounded p-2">
        <div class="text-[10px] text-muted-foreground uppercase">Last 10</div>
        <div
          :class="[
            'font-mono font-bold',
            isUp ? 'text-green-400' : 'text-red-400',
          ]"
        >
          {{ isUp ? "+" : "" }}{{ priceChange.toFixed(1) }}%
          {{ isUp ? "▲" : "▼" }}
        </div>
      </div>
    </div>

    <!-- Amount Input -->
    <div class="space-y-1">
      <label class="text-[10px] text-muted-foreground uppercase">Amount</label>
      <div class="flex items-center gap-2">
        <Input
          v-model.number="amount"
          type="number"
          min="1"
          class="h-8 text-sm font-mono"
          placeholder="100"
          :disabled="isPending"
        />
        <span class="text-sm text-muted-foreground">⚡</span>
      </div>
      <div class="grid grid-cols-2 gap-1 text-[10px] text-muted-foreground">
        <div>Buy: {{ buyCost === "—" ? "N/A" : `≈${buyCost} DYS` }}</div>
        <div>Sell: {{ sellReturn === "—" ? "N/A" : `≈${sellReturn} DYS` }}</div>
      </div>
    </div>

    <!-- Error display -->
    <div v-if="swapError" class="text-[10px] text-red-400 truncate">
      {{ swapError }}
    </div>

    <!-- Buy/Sell Buttons -->
    <div class="grid grid-cols-2 gap-2">
      <div class="flex flex-col gap-1">
        <Button
          variant="outline"
          size="sm"
          class="bg-green-500/10 border-green-500/50 text-green-400 hover:bg-green-500/20 hover:text-green-300"
          :disabled="!canBuy"
          @click="handleBuy"
        >
          <span v-if="isPending">...</span>
          <span v-else>Buy</span>
        </Button>
        <span
          v-if="buyDisabledReason"
          class="text-[9px] text-muted-foreground text-center"
        >
          {{ buyDisabledReason }}
        </span>
      </div>
      <div class="flex flex-col gap-1">
        <Button
          variant="outline"
          size="sm"
          class="bg-red-500/10 border-red-500/50 text-red-400 hover:bg-red-500/20 hover:text-red-300"
          :disabled="!canSell"
          @click="handleSell"
        >
          <span v-if="isPending">...</span>
          <span v-else>Sell</span>
        </Button>
        <span
          v-if="sellDisabledReason"
          class="text-[9px] text-muted-foreground text-center"
        >
          {{ sellDisabledReason }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(.vis-xy-container) {
  width: 100% !important;
  height: 100% !important;
}
</style>
