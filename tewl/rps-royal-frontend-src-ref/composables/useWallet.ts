import { computed, reactive, ref } from "vue";
import axios from "axios";
import {
  DirectSecp256k1HdWallet,
  makeSignDoc,
  executeKdf,
  extractKdfConfiguration,
} from "@cosmjs/proto-signing";
import { useStorage } from "@vueuse/core";
import { getChainInfo, sendMsgs } from "../utils/dysonTxUtils";
import { TxRaw } from "cosmjs-types/cosmos/tx/v1beta1/tx.js";
import { toBase64, fromBase64 } from "@cosmjs/encoding";

const COSMJS_WALLET_TYPE = "cosmjs";

// Shared state across all useWallet() calls
const walletDialogVisible = ref(false);
const chainId = useStorage("rps-chainId", "");
const rpcUrl = useStorage("rps-rpcUrl", "");
const unlockedWallets = useStorage<
  Array<{ name: string; address: string; type: string; _pass?: string }>
>("rps-unlockedWallets", []);
const localCosmJsWallets = useStorage<
  Array<{ name: string; encrypted: string; address: string }>
>("rps-localCosmJsWallets", []);
const gasPrice = useStorage("rps-gasPrice", 0.0);

const state = reactive({
  activeWalletInstance: null as any,
  isLoading: true,
});

let globalKeplrListenerSet = false;

export function useWallet() {
  const restUrl = "";

  const isAnyWalletConnected = computed(() => unlockedWallets.value.length > 0);

  const wallet = computed(
    () => unlockedWallets.value[0] || { address: null, name: null, type: null }
  );

  const init = async () => {
    await loadChainIdFromApi();
    if (!globalKeplrListenerSet && typeof window !== "undefined") {
      window.addEventListener("keplr_keystorechange", handleKeplrAccountChange);
      globalKeplrListenerSet = true;
    }
    await validatePersistedKeplrWallet();
    state.isLoading = false;
  };

  const handleKeplrAccountChange = async () => {
    state.activeWalletInstance = null;
    if (typeof window === "undefined" || !(window as any).keplr) return;
    const keplr = (window as any).keplr;
    await keplr.enable(chainId.value);
    const key = await keplr.getKey(chainId.value);
    const wallets = [...unlockedWallets.value];
    const keplrIndex = wallets.findIndex((w) => w.type === "keplr");
    const newKeplrWallet = {
      name: key.name,
      address: key.bech32Address,
      type: "keplr",
    };
    if (keplrIndex === -1) wallets.push(newKeplrWallet);
    else wallets.splice(keplrIndex, 1, newKeplrWallet);
    unlockedWallets.value = wallets;
    state.activeWalletInstance = keplr.getOfflineSigner(chainId.value);
  };

  const loadChainIdFromApi = async () => {
    const resp = await axios.get("/cosmos/base/tendermint/v1beta1/node_info");
    const json = resp.data;
    const discovered = json?.default_node_info?.network;
    if (!discovered) throw new Error("No chainId found in node_info response.");
    chainId.value = discovered;
    const rawRpcAddr = json?.default_node_info?.other?.rpc_address || "";
    const normalizedRpc = String(rawRpcAddr)
      .trim()
      .replace(/^tcp:\/\//, "http://");
    if (normalizedRpc) rpcUrl.value = normalizedRpc;
  };

  const suggestChainIfNeeded = async (provider: any) => {
    const name = chainId.value.includes("mainnet")
      ? "DysonProtocol2"
      : `DysonProtocol2 (${chainId.value.split("-").slice(1, -1).join("-")})`;

    const chainInfo = {
      chainId: chainId.value,
      chainName: name,
      rpc: rpcUrl.value,
      rest: restUrl || window.location.origin,
      bip44: { coinType: 118 },
      bech32Config: {
        bech32PrefixAccAddr: "dys2",
        bech32PrefixAccPub: "dys2pub",
        bech32PrefixValAddr: "dys2valoper",
        bech32PrefixValPub: "dys2valoperpub",
        bech32PrefixConsAddr: "dys2valcons",
        bech32PrefixConsPub: "dys2valconspub",
      },
      currencies: [
        { coinDenom: "DYS2", coinMinimalDenom: "udys", coinDecimals: 6 },
      ],
      feeCurrencies: [
        {
          coinDenom: "DYS2",
          coinMinimalDenom: "udys",
          coinDecimals: 6,
          gasPriceStep: { low: 0.0, average: 0.0, high: 0.00002 },
        },
      ],
      stakeCurrency: {
        coinDenom: "DYS2",
        coinMinimalDenom: "udys",
        coinDecimals: 6,
      },
    };

    try {
      await provider.enable(chainId.value);
    } catch {
      await provider.experimentalSuggestChain(chainInfo);
      await provider.enable(chainId.value);
    }
  };

  const validatePersistedKeplrWallet = async () => {
    const idx = unlockedWallets.value.findIndex((w) => w.type === "keplr");
    if (idx === -1) return;

    if (typeof window === "undefined" || !(window as any).keplr) {
      unlockedWallets.value.splice(idx, 1);
      state.activeWalletInstance = null;
      return;
    }

    try {
      const keplr = (window as any).keplr;
      await suggestChainIfNeeded(keplr);
      const key = await keplr.getKey(chainId.value);
      unlockedWallets.value.splice(idx, 1, {
        name: key.name,
        address: key.bech32Address,
        type: "keplr",
      });
      state.activeWalletInstance = keplr.getOfflineSigner(chainId.value);
    } catch {
      unlockedWallets.value.splice(idx, 1);
      state.activeWalletInstance = null;
    }
  };

  const connectExtension = async (type: string) => {
    const provider =
      type === "keplr"
        ? typeof window !== "undefined"
          ? (window as any).keplr
          : null
        : null;
    if (!provider) throw new Error(`Extension not found: ${type}`);
    await loadChainIdFromApi();
    await suggestChainIfNeeded(provider);
    const offlineSigner = provider.getOfflineSigner(chainId.value);
    const { name, bech32Address: address } = await provider.getKey(
      chainId.value
    );
    const existingIndex = unlockedWallets.value.findIndex(
      (w) => w.address === address
    );
    state.activeWalletInstance = offlineSigner;
    if (existingIndex === -1) {
      unlockedWallets.value.push({
        name: String(name),
        address: String(address),
        type: String(type),
      });
    }
    walletDialogVisible.value = false;
  };

  const importNamedCosmJsWallet = async (
    name: string,
    mnemonic: string,
    password: string
  ) => {
    if (!name.trim()) throw new Error("Wallet name is required.");
    if (!mnemonic.trim()) throw new Error("Mnemonic is empty.");
    if (!password.trim()) throw new Error("Password is required.");
    if (localCosmJsWallets.value.find((w) => w.name === name.trim())) {
      throw new Error(`Wallet "${name}" already exists.`);
    }
    const wallet = await DirectSecp256k1HdWallet.fromMnemonic(mnemonic, {
      prefix: "dys2",
    });
    const kdfConfig = {
      algorithm: "argon2id" as const,
      params: { outputLength: 32, opsLimit: 24, memLimitKib: 12 * 1024 },
    };
    const encryptionKey = await executeKdf(password, kdfConfig);
    const encrypted = await wallet.serializeWithEncryptionKey(
      encryptionKey,
      kdfConfig
    );
    const address = (await wallet.getAccounts())[0].address;
    localCosmJsWallets.value.push({ name: name.trim(), encrypted, address });
    unlockedWallets.value.push({
      name: name.trim(),
      address,
      type: COSMJS_WALLET_TYPE,
      _pass: password,
    });
    state.activeWalletInstance = wallet;
    walletDialogVisible.value = false;
  };

  const connectNamedCosmJsWallet = async (name: string, password: string) => {
    const walletData = localCosmJsWallets.value.find((w) => w.name === name);
    if (!walletData) throw new Error(`No local wallet named "${name}".`);
    if (!password.trim())
      throw new Error("Password required to unlock wallet.");
    const kdfConf = extractKdfConfiguration(walletData.encrypted);
    const encryptionKey = await executeKdf(password, kdfConf);
    const wallet = await DirectSecp256k1HdWallet.deserializeWithEncryptionKey(
      walletData.encrypted,
      encryptionKey
    );
    state.activeWalletInstance = wallet;
    const address = (await wallet.getAccounts())[0].address;
    const existingIndex = unlockedWallets.value.findIndex(
      (w) => w.name === name
    );
    if (existingIndex === -1) {
      unlockedWallets.value.push({
        name,
        address,
        type: COSMJS_WALLET_TYPE,
        _pass: password,
      });
    } else {
      unlockedWallets.value[existingIndex]._pass = password;
    }
    walletDialogVisible.value = false;
  };

  const generateMnemonic = async (length = 24) => {
    const wallet = await DirectSecp256k1HdWallet.generate(length);
    return wallet.mnemonic;
  };

  const buildFee = (gasLimit: number) => {
    const limit = Number(gasLimit) || 200000;
    const price = Number(gasPrice.value) || 0;
    const totalAmount = Math.floor(limit * price);
    return {
      amount: [{ denom: "udys", amount: String(totalAmount) }],
      gas_limit: String(limit),
    };
  };

  const getWallet = async (overrideAddress: string) => {
    const effective = unlockedWallets.value.find(
      (u) => u.address === overrideAddress
    );
    if (!effective) throw new Error("Requested wallet is not unlocked.");

    if (effective.type === "keplr") {
      const provider = (window as any).keplr;
      if (!provider) throw new Error("Keplr extension not found.");
      await suggestChainIfNeeded(provider);
      const offlineSigner = provider.getOfflineSigner(chainId.value);
      const [{ address: signerAddr }] = await offlineSigner.getAccounts();
      if (signerAddr !== overrideAddress) {
        throw new Error(
          `Address mismatch: requested address (${overrideAddress}) is not active in Keplr.`
        );
      }
      state.activeWalletInstance = offlineSigner;
    } else if (effective.type === COSMJS_WALLET_TYPE) {
      const unlocked = unlockedWallets.value.find(
        (u) => u.address === overrideAddress
      );
      if (!unlocked?._pass)
        throw new Error(
          "Wallet session expired. Please unlock the wallet again."
        );
      const walletData = localCosmJsWallets.value.find(
        (w) => w.name === effective.name
      );
      if (!walletData)
        throw new Error("Wallet data not found. Please reconnect your wallet.");
      const kdfConf = extractKdfConfiguration(walletData.encrypted);
      const encryptionKey = await executeKdf(unlocked._pass, kdfConf);
      const wallet = await DirectSecp256k1HdWallet.deserializeWithEncryptionKey(
        walletData.encrypted,
        encryptionKey
      );
      state.activeWalletInstance = wallet;
    }

    if (!state.activeWalletInstance)
      throw new Error("Wallet session expired. Please reconnect your wallet.");
    return { ...effective, walletInstance: state.activeWalletInstance };
  };

  const GAS_CEILING = 100_000_000;
  const GAS_MULTIPLIER = 1.3;

  const sendMsg = async ({
    msg,
    msgs,
    gasLimit,
    memo = "",
    executorAddress,
  }: {
    msg?: any;
    msgs?: any[];
    gasLimit?: number | "auto";
    memo?: string;
    executorAddress: string;
  }) => {
    const { walletInstance, address, type } = await getWallet(executorAddress);
    const baseMsgs =
      Array.isArray(msgs) && msgs.length > 0 ? msgs : msg ? [msg] : [];
    if (baseMsgs.length === 0)
      throw new Error("sendMsg requires msg or msgs[]");

    let finalGasLimit: number;
    if (typeof gasLimit === "number") {
      finalGasLimit = gasLimit;
    } else {
      // Auto gas: simulate first to estimate
      const simResult = await sendMsgs({
        apiUrl: restUrl,
        wallet: walletInstance,
        walletType: type,
        address,
        msgs: baseMsgs,
        memo,
        fee: buildFee(GAS_CEILING),
        simulate: true,
      });
      if (!simResult.success) return simResult; // Simulation failed, return error
      const gasUsed = parseInt(
        simResult.raw?.gas_info?.gas_used ?? simResult.gasUsed ?? "0"
      );
      finalGasLimit =
        gasUsed > 0 ? Math.round(gasUsed * GAS_MULTIPLIER) : GAS_CEILING;
    }

    const fee = buildFee(finalGasLimit);
    const result = await sendMsgs({
      apiUrl: restUrl,
      wallet: walletInstance,
      walletType: type,
      address,
      msgs: baseMsgs,
      memo,
      fee,
      simulate: false,
    });
    return result;
  };

  const signOut = () => {
    unlockedWallets.value = [];
    state.activeWalletInstance = null;
  };

  const openWalletDialog = () => {
    walletDialogVisible.value = true;
  };

  const closeWalletDialog = () => {
    walletDialogVisible.value = false;
  };

  return {
    wallet,
    chainId,
    rpcUrl,
    unlockedWallets,
    localCosmJsWallets,
    isAnyWalletConnected,
    walletDialogVisible,
    state,
    init,
    connectExtension,
    importNamedCosmJsWallet,
    connectNamedCosmJsWallet,
    generateMnemonic,
    signOut,
    openWalletDialog,
    closeWalletDialog,
    getWallet,
    sendMsg,
    buildFee,
  };
}
