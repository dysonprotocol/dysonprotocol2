<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { toast } from "vue-sonner";
import axios from "axios";
import { useWallet } from "@/composables/useWallet";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { SCRIPT_ADDRESS } from "@/types/game";

const router = useRouter();
const { wallet, openWalletDialog, sendMsg, importNamedCosmJsWallet, init } =
  useWallet();

async function queryPiece(pieceId: number): Promise<any> {
  const index = `game/pieces/${String(pieceId).padStart(10, "0")}`;
  const url = `/dysonprotocol/storage/v1/storage_get?owner=${SCRIPT_ADDRESS}&index=${encodeURIComponent(
    index
  )}`;
  const resp = await axios.get(url);
  return JSON.parse(resp.data.entry.data);
}

const scriptCode = ref("");
const isDeploying = ref(false);
const deployResult = ref<any>(null);
const forceInit = ref(false);

// Snail management
const snailStatus = ref<any>(null);
const isSnailLoading = ref(false);
const SNAIL_ID = 0;

// Alice's mnemonic for the script address
const ALICE_MNEMONIC =
  "public feature teach face federal matrix throw legend bridge brass diary beach typical doll evoke weapon among crane regret trust enact swarm brother outside";

const address = computed(() => wallet.value?.address || null);
const isAliceConnected = computed(() => address.value === SCRIPT_ADDRESS);

onMounted(async () => {
  await init();
  await loadScript();
  await checkSnailStatus();
});

async function loadScript() {
  const resp = await fetch("/script.py");
  if (resp.ok) {
    scriptCode.value = await resp.text();
  } else {
    toast.error("Failed to load script.py");
  }
}

async function connectAlice() {
  try {
    await importNamedCosmJsWallet("alice", ALICE_MNEMONIC, "alice123");
    toast.success("Connected as Alice");
  } catch (err: any) {
    if (err.message?.includes("already exists")) {
      toast.info(
        'Alice wallet already imported. Enter password "alice123" to unlock.'
      );
    } else {
      toast.error(err.message);
    }
  }
}

async function deployScript() {
  if (!isAliceConnected.value) {
    toast.error("Connect Alice wallet first");
    return;
  }

  isDeploying.value = true;
  deployResult.value = null;

  try {
    const msg = {
      "@type": "/dysonprotocol.script.v1.MsgUpdateScript",
      address: SCRIPT_ADDRESS,
      code: scriptCode.value,
    };

    const result = await sendMsg({
      msg,
      gasLimit: 5000000,
      executorAddress: SCRIPT_ADDRESS,
    });

    deployResult.value = result;

    if (result.success) {
      toast.success("Script deployed successfully!");
    } else {
      toast.error(`Deploy failed: ${result.rawLog || "Unknown error"}`);
    }
  } catch (err: any) {
    toast.error(err.message);
    deployResult.value = { success: false, rawLog: err.message };
  } finally {
    isDeploying.value = false;
  }
}

async function initializeGame() {
  if (!isAliceConnected.value) {
    toast.error("Connect Alice wallet first");
    return;
  }

  isDeploying.value = true;
  deployResult.value = null;

  try {
    const msg = {
      "@type": "/dysonprotocol.script.v1.MsgExec",
      executor_address: SCRIPT_ADDRESS,
      script_address: SCRIPT_ADDRESS,
      function_name: "initialize_game",
      args: "[]",
      kwargs: JSON.stringify({ force: forceInit.value }),
      extra_code: "",
      attached_messages: [],
    };

    const result = await sendMsg({
      msg,
      gasLimit: 15000000, // Force init needs more gas for storage deletes
      executorAddress: SCRIPT_ADDRESS,
    });

    deployResult.value = result;

    if (result.success) {
      toast.success("Game initialized!");
      await checkSnailStatus();
    } else {
      toast.error(`Init failed: ${result.rawLog || "Unknown error"}`);
    }
  } catch (err: any) {
    toast.error(err.message);
    deployResult.value = { success: false, rawLog: err.message };
  } finally {
    isDeploying.value = false;
  }
}

async function checkSnailStatus() {
  isSnailLoading.value = true;
  try {
    const piece = await queryPiece(SNAIL_ID);
    snailStatus.value = piece;
  } catch {
    snailStatus.value = null;
  } finally {
    isSnailLoading.value = false;
  }
}

async function spawnSnail() {
  if (!isAliceConnected.value) {
    toast.error("Connect Alice wallet first");
    return;
  }

  isDeploying.value = true;
  deployResult.value = null;

  try {
    const msg = {
      "@type": "/dysonprotocol.script.v1.MsgExec",
      executor_address: SCRIPT_ADDRESS,
      script_address: SCRIPT_ADDRESS,
      function_name: "spawn_snail",
      args: "[]",
      kwargs: "{}",
      extra_code: "",
      attached_messages: [],
    };

    const result = await sendMsg({
      msg,
      executorAddress: SCRIPT_ADDRESS,
    });

    deployResult.value = result;

    if (result.success) {
      toast.success("🐌 Snail spawned! Crontask heartbeat scheduled.");
      await checkSnailStatus();
    } else {
      toast.error(`Spawn failed: ${result.rawLog || "Unknown error"}`);
    }
  } catch (err: any) {
    toast.error(err.message);
    deployResult.value = { success: false, rawLog: err.message };
  } finally {
    isDeploying.value = false;
  }
}

async function triggerSnailHeartbeat() {
  if (!isAliceConnected.value) {
    toast.error("Connect Alice wallet first");
    return;
  }

  isDeploying.value = true;
  deployResult.value = null;

  try {
    const msg = {
      "@type": "/dysonprotocol.script.v1.MsgExec",
      executor_address: SCRIPT_ADDRESS,
      script_address: SCRIPT_ADDRESS,
      function_name: "snail_heartbeat",
      args: "[]",
      kwargs: "{}",
      extra_code: "",
      attached_messages: [],
    };

    const result = await sendMsg({
      msg,
      gasLimit: 5000000,
      executorAddress: SCRIPT_ADDRESS,
    });

    deployResult.value = result;

    if (result.success) {
      toast.success("Snail heartbeat triggered");
      await checkSnailStatus();
    } else {
      toast.error(`Heartbeat failed: ${result.rawLog || "Unknown error"}`);
    }
  } catch (err: any) {
    toast.error(err.message);
    deployResult.value = { success: false, rawLog: err.message };
  } finally {
    isDeploying.value = false;
  }
}

async function moveSnailManually() {
  if (!isAliceConnected.value) {
    toast.error("Connect Alice wallet first");
    return;
  }

  isDeploying.value = true;
  deployResult.value = null;

  try {
    const msg = {
      "@type": "/dysonprotocol.script.v1.MsgExec",
      executor_address: SCRIPT_ADDRESS,
      script_address: SCRIPT_ADDRESS,
      function_name: "move_snail_ai",
      args: "[]",
      kwargs: "{}",
      extra_code: "",
      attached_messages: [],
    };

    const result = await sendMsg({
      msg,
      gasLimit: 10000000,
      executorAddress: SCRIPT_ADDRESS,
    });

    deployResult.value = result;

    if (result.success) {
      toast.success("🐌 Snail moved!");
      await checkSnailStatus();
    } else {
      toast.error(`Move failed: ${result.rawLog || "Unknown error"}`);
    }
  } catch (err: any) {
    toast.error(err.message);
    deployResult.value = { success: false, rawLog: err.message };
  } finally {
    isDeploying.value = false;
  }
}
</script>

<template>
  <div class="fixed inset-0 bg-background p-6 overflow-y-auto">
    <div class="max-w-4xl mx-auto space-y-6">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <h1 class="text-2xl font-bold">Deploy RPS Script</h1>
        <Button variant="outline" size="sm" @click="router.push('/')">
          ← Back to Game
        </Button>
      </div>

      <!-- Wallet Status -->
      <div class="p-4 rounded-lg border border-border bg-card">
        <h2 class="font-semibold mb-3">Wallet Status</h2>

        <div class="space-y-2 text-sm">
          <div class="flex items-center justify-between">
            <span class="text-muted-foreground">Script Address:</span>
            <code class="font-mono text-xs bg-secondary px-2 py-0.5 rounded">{{
              SCRIPT_ADDRESS
            }}</code>
          </div>

          <div class="flex items-center justify-between">
            <span class="text-muted-foreground">Connected:</span>
            <span
              :class="isAliceConnected ? 'text-green-500' : 'text-yellow-500'"
            >
              {{
                isAliceConnected
                  ? "✓ Alice (Script Owner)"
                  : address
                  ? `${address.slice(0, 12)}... (Not Alice)`
                  : "Not connected"
              }}
            </span>
          </div>
        </div>

        <div class="mt-4 flex gap-2">
          <Button v-if="!isAliceConnected" @click="connectAlice" size="sm">
            Connect as Alice
          </Button>
          <Button
            v-if="!address"
            variant="outline"
            size="sm"
            @click="openWalletDialog"
          >
            Other Wallet
          </Button>
        </div>
      </div>

      <!-- Script Preview -->
      <div class="p-4 rounded-lg border border-border bg-card">
        <div class="flex items-center justify-between mb-3">
          <h2 class="font-semibold">Script Code</h2>
          <span class="text-xs text-muted-foreground"
            >{{ scriptCode.length.toLocaleString() }} chars</span
          >
        </div>

        <pre
          class="text-xs font-mono bg-secondary/50 p-3 rounded max-h-64 overflow-auto whitespace-pre-wrap"
          >{{ scriptCode.slice(0, 2000)
          }}{{ scriptCode.length > 2000 ? "\n\n... (truncated)" : "" }}</pre
        >
      </div>

      <!-- Actions -->
      <div class="p-4 rounded-lg border border-border bg-card space-y-4">
        <h2 class="font-semibold">Actions</h2>

        <div class="flex gap-3">
          <Button
            @click="deployScript"
            :disabled="!isAliceConnected || isDeploying"
            class="flex-1"
          >
            {{ isDeploying ? "Deploying..." : "Deploy Script" }}
          </Button>

          <Button
            variant="outline"
            @click="initializeGame"
            :disabled="!isAliceConnected || isDeploying"
          >
            Initialize Game
          </Button>

          <label class="flex items-center gap-2 cursor-pointer">
            <Checkbox v-model="forceInit" />
            <span class="text-sm">Force (clear all data)</span>
          </label>
        </div>

        <p class="text-xs text-muted-foreground">
          Deploy will update the script at {{ SCRIPT_ADDRESS }}. Initialize
          creates the game state (run once after deploy).
          <span v-if="forceInit" class="text-amber-500 font-medium">
            ⚠ Force will delete all pieces, grid, and player data!</span
          >
        </p>
      </div>

      <!-- Snail Management -->
      <div class="p-4 rounded-lg border border-border bg-card space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="font-semibold">🐌 Snail NPC Management</h2>
          <Button
            variant="ghost"
            size="sm"
            @click="checkSnailStatus"
            :disabled="isSnailLoading"
          >
            {{ isSnailLoading ? "Loading..." : "Refresh" }}
          </Button>
        </div>

        <!-- Snail Status -->
        <div class="p-3 rounded bg-secondary/50 space-y-2">
          <div class="flex items-center justify-between text-sm">
            <span class="text-muted-foreground">Status:</span>
            <span
              :class="snailStatus ? 'text-green-500' : 'text-yellow-500'"
              class="font-medium"
            >
              {{ snailStatus ? "🐌 Active" : "Not spawned" }}
            </span>
          </div>

          <template v-if="snailStatus">
            <div class="flex items-center justify-between text-sm">
              <span class="text-muted-foreground">Position:</span>
              <code class="font-mono text-xs bg-background px-2 py-0.5 rounded">
                ({{ snailStatus.x }}, {{ snailStatus.y }})
              </code>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-muted-foreground">Last Action Block:</span>
              <code class="font-mono text-xs bg-background px-2 py-0.5 rounded">
                {{ snailStatus.last_action_block }}
              </code>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-muted-foreground">Spawn Block:</span>
              <code class="font-mono text-xs bg-background px-2 py-0.5 rounded">
                {{ snailStatus.spawn_block }}
              </code>
            </div>
          </template>
        </div>

        <!-- Snail Actions -->
        <div class="flex gap-2 flex-wrap">
          <Button
            v-if="!snailStatus"
            @click="spawnSnail"
            :disabled="!isAliceConnected || isDeploying"
            size="sm"
          >
            Spawn Snail
          </Button>

          <template v-if="snailStatus">
            <Button
              variant="outline"
              @click="triggerSnailHeartbeat"
              :disabled="!isAliceConnected || isDeploying"
              size="sm"
            >
              Trigger Heartbeat
            </Button>
            <Button
              variant="outline"
              @click="moveSnailManually"
              :disabled="!isAliceConnected || isDeploying"
              size="sm"
            >
              Move Now
            </Button>
          </template>
        </div>

        <p class="text-xs text-muted-foreground">
          The snail is an NPC that hunts the oldest player. Once spawned, it
          uses crontask to schedule automatic movement every ~10 seconds.
          <span v-if="snailStatus" class="text-green-500/80">
            Crontask is running automatically.</span
          >
        </p>
      </div>

      <!-- Result -->
      <div
        v-if="deployResult"
        class="p-4 rounded-lg border bg-card"
        :class="
          deployResult.success ? 'border-green-500/50' : 'border-red-500/50'
        "
      >
        <h2
          class="font-semibold mb-2"
          :class="deployResult.success ? 'text-green-500' : 'text-red-500'"
        >
          {{ deployResult.success ? "✓ Success" : "✕ Failed" }}
        </h2>
        <pre
          class="text-xs font-mono bg-secondary/50 p-2 rounded overflow-auto max-h-48"
          >{{ JSON.stringify(deployResult, null, 2) }}</pre
        >
      </div>
    </div>
  </div>
</template>
