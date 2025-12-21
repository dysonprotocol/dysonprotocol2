<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { useWallet } from "@/composables/useWallet";
import { useScript } from "@/composables/useScript";
import { getBalance } from "@/lib/tewl";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";

const router = useRouter();
const { wallet } = useWallet();
const { createRequest: doCreateRequest } = useScript();

const prompt = ref("What time is it in New York?");
const responseSchema = ref('{"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}');
const scorer = ref(`def scorer(reveal, state):
    if state is None:
        state = {"result": None, "scores": {}, "responses": []}
    state["responses"].append(reveal["response"])
    state["scores"][reveal["provider"]] = 1.0
    if state["result"] is None:
        state["result"] = reveal["response"]
    return state`);
const fee = ref("1");
const callbackScript = ref("");
const callbackFn = ref("");
const showAdvanced = ref(false);

const txPending = ref(false);
const error = ref<string | null>(null);
const balance = ref<string>("0");

const insufficientFunds = computed(() => {
  const bal = BigInt(balance.value || "0");
  const required = BigInt(fee.value || "0");
  return bal < required;
});

async function loadBalance() {
  if (!wallet.value.address) return;
  balance.value = await getBalance(wallet.value.address);
}

watch(() => wallet.value.address, loadBalance, { immediate: true });

async function handleSubmit() {
  if (insufficientFunds.value) {
    error.value = `Insufficient funds: you have ${balance.value} udys but need ${fee.value} udys`;
    return;
  }

  txPending.value = true;
  error.value = null;

  try {
    const schemaObj = JSON.parse(responseSchema.value);
    await doCreateRequest(
        prompt.value,
        schemaObj,
        scorer.value,
      fee.value,
      callbackScript.value || undefined,
      callbackFn.value || undefined
    );
    router.push("/");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    txPending.value = false;
  }
}
</script>

<template>
  <div class="max-w-2xl space-y-6">
    <h1 class="text-2xl font-bold">Create Request</h1>

    <Card v-if="!wallet.address" class="p-4">Connect wallet to continue</Card>

    <template v-else>
      <Card v-if="insufficientFunds" class="p-4 bg-destructive/10 border-destructive">
        <p class="text-destructive font-medium">Insufficient funds</p>
        <p class="text-sm text-muted-foreground mt-1">
          Your balance: {{ balance }} udys • Required: {{ fee }} udys
        </p>
      </Card>

      <div v-if="error" class="p-4 bg-destructive/10 text-destructive rounded-lg">
        {{ error }}
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
      <div class="space-y-2">
        <Label>Prompt</Label>
        <Input v-model="prompt" required placeholder="What time is it in New York?" />
      </div>

      <div class="space-y-2">
        <Label>Response Schema (JSON Schema)</Label>
        <Textarea v-model="responseSchema" rows="4" required class="font-mono text-sm" />
      </div>

      <div class="space-y-2">
        <Label>Scorer (Python)</Label>
          <Textarea v-model="scorer" rows="10" required class="font-mono text-sm" />
        <p class="text-xs text-muted-foreground">
          Function signature: def scorer(reveal, state) -> state
        </p>
      </div>

        <div class="space-y-2">
          <Label>Fee (udys)</Label>
          <Input v-model="fee" required />
          <p class="text-xs text-muted-foreground">
            Timeouts: 30s per phase or 100% provider participation
          </p>
        </div>

        <button type="button" @click="showAdvanced = !showAdvanced" class="text-sm text-primary hover:underline">
          {{ showAdvanced ? '− Hide' : '+ Show' }} Advanced Options
        </button>

        <div v-if="showAdvanced" class="space-y-4 p-4 bg-muted/50 rounded-lg">
          <div class="space-y-2">
            <Label>Callback Script (optional)</Label>
            <Input v-model="callbackScript" placeholder="dys1..." />
            <p class="text-xs text-muted-foreground">
              Script address to call when request is finalized
            </p>
          </div>
          <div class="space-y-2">
            <Label>Callback Function (optional)</Label>
            <Input v-model="callbackFn" placeholder="on_tewl_result" />
            <p class="text-xs text-muted-foreground">
              Function name to call with (request_id, result) args
            </p>
        </div>
      </div>

      <Button type="submit" :disabled="txPending || insufficientFunds" class="w-full">
        {{ txPending ? "Creating..." : "Create Request" }}
      </Button>
    </form>
    </template>
  </div>
</template>
