import { useWallet } from "./useWallet";
import { getScriptAddress } from "@/lib/tewl";

// Parse script error from raw_log or scriptResponse
function parseScriptError(result: any): string {
  // Try scriptResponse.exception first (has structured error)
  const exception = result.scriptResponse?.exception;
  if (exception) {
    // exception might be an object with msg field, or a string
    if (typeof exception === "object" && exception.msg) {
      return exception.msg;
    }
    if (typeof exception === "string") {
      return exception;
    }
  }

  // Try to parse from rawLog
  const rawLog = result.rawSendMsgsResponse?.rawLog || result.rawLog;
  if (rawLog) {
    // Try to extract the exception.msg from the JSON in rawLog
    // Format: "failed to execute message; message index: 0: {\"exception\":{\"msg\":\"...\"}}: script execution error"
    try {
      const jsonMatch = rawLog.match(/\{[^{}]*"exception"[^{}]*\{[^}]+\}[^}]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0].replace(/\\/g, ""));
        if (parsed.exception?.msg) {
          return parsed.exception.msg;
        }
      }
    } catch {
      // Fall through to simpler parsing
    }

    // Try simpler regex to extract the msg value
    const msgMatch = rawLog.match(/"msg":\s*"([^"]+)"/);
    if (msgMatch) {
      // Unescape the message
      return msgMatch[1].replace(/\\'/g, "'").replace(/\\"/g, '"');
    }

    // Return cleaned up rawLog
    if (rawLog.length > 200) {
      // Extract just the error class and message
      const errorMatch = rawLog.match(/(\w+Error)\(['"]([^'"]+)['"]\)/);
      if (errorMatch) {
        return `${errorMatch[1]}: ${errorMatch[2]}`;
      }
    }
    return rawLog;
  }

  return "Transaction failed";
}

export function useScript() {
  const { wallet, sendMsg } = useWallet();
  const scriptAddress = getScriptAddress();

  async function exec(
    fn: string,
    args: unknown[] = [],
    attachedCoins: { denom: string; amount: string }[] = []
  ) {
    if (!wallet.value.address) throw new Error("Wallet not connected");

    const attachedMessages = attachedCoins.map((coin) => ({
      "@type": "/cosmos.bank.v1beta1.MsgSend",
      from_address: wallet.value.address,
      to_address: scriptAddress,
      amount: [coin],
    }));

    const msg = {
      "@type": "/dysonprotocol.script.v1.MsgExec",
      executor_address: wallet.value.address,
      script_address: scriptAddress,
      script_name: "",
      extra_code: "",
      function_name: fn,
      args: JSON.stringify(args),
      kwargs: "{}",
      attached_messages: attachedMessages,
    };

    const result = await sendMsg({
      msg,
      gasLimit: "auto",
      executorAddress: wallet.value.address,
    });

    if (!result.success) {
      throw new Error(parseScriptError(result));
    }

    return result;
  }

  // Script function wrappers
  const depositBond = (amount: string) =>
    exec("deposit_bond", [], [{ denom: "udys", amount }]);

  const withdrawBond = (amount: string) => exec("withdraw_bond", [amount]);

  const createRequest = (
    prompt: string,
    schema: object,
    scorer: string,
    fee: string,
    callbackScript?: string,
    callbackFn?: string
  ) =>
    exec(
      "create_request",
      [prompt, schema, scorer, callbackScript || "", callbackFn || ""],
      [{ denom: "udys", amount: fee }]
    );

  const commit = (requestId: number, hash: string) =>
    exec("commit", [requestId, hash]);

  const reveal = (requestId: number, response: unknown, salt: string) =>
    exec("reveal", [requestId, response, salt]);

  const finalize = (requestId: number) => exec("finalize", [requestId]);

  // Admin functions
  const setMinBond = (amount: string) => exec("set_min_bond", [amount]);
  const resetAll = () => exec("reset_all", []);

  return {
    exec,
    depositBond,
    withdrawBond,
    createRequest,
    commit,
    reveal,
    finalize,
    setMinBond,
    resetAll,
  };
}

