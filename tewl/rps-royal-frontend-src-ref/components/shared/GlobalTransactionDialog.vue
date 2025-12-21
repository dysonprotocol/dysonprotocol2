<template>
  <Dialog v-model:open="isOpen" @update:open="onOpenChange">
    <DialogScrollContent class="max-w-3xl w-full md:max-w-3xl">
      <DialogHeader>
        <DialogTitle>Confirm Transaction</DialogTitle>
        <DialogDescription>
          Review and edit the transaction before signing.
        </DialogDescription>
      </DialogHeader>

      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium mb-1">Chain ID</label>
          <Input v-model="form.chainId" placeholder="chain-id" class="h-9" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Address</label>
          <Input v-model="form.address" placeholder="dys2..." class="h-9" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Messages (JSON)</label>
          <textarea
            v-model="form.msgsText"
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono min-h-40"
            spellcheck="false"
          />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Fee (JSON)</label>
          <textarea
            v-model="form.feeText"
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono min-h-24"
            spellcheck="false"
          />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Memo</label>
          <Input v-model="form.memo" placeholder="optional memo" class="h-9" />
        </div>

        <div v-if="errorMessage" class="text-destructive text-xs">
          {{ errorMessage }}
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="cancel">Cancel</Button>
        <Button @click="confirm">Confirm</Button>
      </DialogFooter>
    </DialogScrollContent>
  </Dialog>
</template>

<script setup>
import { ref } from "vue";
import { transactionConfig } from "@/utils/transactionModalConfig.js";
import {
  Dialog,
  DialogScrollContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const isOpen = ref(false);
const resolver = ref(null);
const errorMessage = ref("");
const form = ref({
  chainId: "",
  address: "",
  msgsText: "[]",
  feeText: '{"amount":[],"gas_limit":"200000"}',
  memo: "",
});

transactionConfig.modalHandler = (msgs, memo, fee, chainId, address) => {
  return new Promise((resolve) => {
    resolver.value = resolve;
    errorMessage.value = "";
    form.value.chainId = chainId || "";
    form.value.address = address || "";
    try {
      form.value.msgsText = JSON.stringify(msgs ?? [], null, 2);
    } catch {
      form.value.msgsText = "[]";
    }
    try {
      form.value.feeText = JSON.stringify(
        fee ?? { amount: [], gas_limit: "200000" },
        null,
        2
      );
    } catch {
      form.value.feeText = '{"amount":[],"gas_limit":"200000"}';
    }
    form.value.memo = memo || "";
    isOpen.value = true;
  });
};

function cancel() {
  if (resolver.value) resolver.value(null);
  resolver.value = null;
  isOpen.value = false;
}

function confirm() {
  errorMessage.value = "";
  try {
    const parsedMsgs = JSON.parse(form.value.msgsText || "[]");
    const parsedFee = JSON.parse(
      form.value.feeText || '{"amount":[],"gas_limit":"200000"}'
    );
    const res = {
      msgs: parsedMsgs,
      memo: form.value.memo || "",
      fee: parsedFee,
      chainId: form.value.chainId || "",
      address: form.value.address || "",
    };
    if (resolver.value) resolver.value(res);
    resolver.value = null;
    isOpen.value = false;
  } catch (e) {
    errorMessage.value = e?.message || "Invalid JSON in messages or fee.";
  }
}

function onOpenChange(nextOpen) {
  if (!nextOpen) cancel();
}
</script>
