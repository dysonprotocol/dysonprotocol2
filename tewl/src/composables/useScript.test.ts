import { describe, it, expect, vi, beforeEach } from "vitest";
import { ref } from "vue";

// Mock useWallet
const mockSendMsg = vi.fn();
const mockWallet = ref({ address: "dys2testaddr" });

vi.mock("./useWallet", () => ({
  useWallet: () => ({
    wallet: mockWallet,
    sendMsg: mockSendMsg,
  }),
}));

// Mock tewl lib
vi.mock("@/lib/tewl", () => ({
  getScriptAddress: () => "dys2script",
}));

import { useScript } from "./useScript";

describe("useScript", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWallet.value = { address: "dys2testaddr" };
    mockSendMsg.mockResolvedValue({ success: true });
  });

  it("throws error when wallet not connected", async () => {
    mockWallet.value = { address: null } as any;
    const { depositBond } = useScript();
    await expect(depositBond("100")).rejects.toThrow("Wallet not connected");
  });

  it("builds correct message for depositBond", async () => {
    const { depositBond } = useScript();
    await depositBond("1000");

    expect(mockSendMsg).toHaveBeenCalledWith({
      msg: expect.objectContaining({
        "@type": "/dysonprotocol.script.v1.MsgExec",
        function_name: "deposit_bond",
        args: "[]",
        attached_messages: [
          expect.objectContaining({
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            amount: [{ denom: "udys", amount: "1000" }],
          }),
        ],
      }),
      gasLimit: "auto",
      executorAddress: "dys2testaddr",
    });
  });

  it("builds correct message for withdrawBond", async () => {
    const { withdrawBond } = useScript();
    await withdrawBond("500");

    expect(mockSendMsg).toHaveBeenCalledWith({
      msg: expect.objectContaining({
        function_name: "withdraw_bond",
        args: '["500"]',
        attached_messages: [],
      }),
      gasLimit: "auto",
      executorAddress: "dys2testaddr",
    });
  });

  it("builds correct message for createRequest", async () => {
    const { createRequest } = useScript();
    await createRequest("What time?", { type: "object" }, "def scorer(): pass", "100");

    expect(mockSendMsg).toHaveBeenCalledWith({
      msg: expect.objectContaining({
        function_name: "create_request",
        args: '["What time?",{"type":"object"},"def scorer(): pass","",""]',
        attached_messages: [
          expect.objectContaining({
            amount: [{ denom: "udys", amount: "100" }],
          }),
        ],
      }),
      gasLimit: "auto",
      executorAddress: "dys2testaddr",
    });
  });

  it("builds correct message for createRequest with callback", async () => {
    const { createRequest } = useScript();
    await createRequest("Prompt", {}, "def s(): pass", "50", "dys1callback", "on_result");

    expect(mockSendMsg).toHaveBeenCalledWith({
      msg: expect.objectContaining({
        function_name: "create_request",
        args: '["Prompt",{},"def s(): pass","dys1callback","on_result"]',
      }),
      gasLimit: "auto",
      executorAddress: "dys2testaddr",
    });
  });

  it("builds correct message for commit", async () => {
    const { commit } = useScript();
    await commit(5, "hash123");

    expect(mockSendMsg).toHaveBeenCalledWith({
      msg: expect.objectContaining({
        function_name: "commit",
        args: '[5,"hash123"]',
      }),
      gasLimit: "auto",
      executorAddress: "dys2testaddr",
    });
  });

  it("builds correct message for reveal", async () => {
    const { reveal } = useScript();
    await reveal(5, { answer: "42" }, "salt123");

    expect(mockSendMsg).toHaveBeenCalledWith({
      msg: expect.objectContaining({
        function_name: "reveal",
        args: '[5,{"answer":"42"},"salt123"]',
      }),
      gasLimit: "auto",
      executorAddress: "dys2testaddr",
    });
  });

  it("builds correct message for finalize", async () => {
    const { finalize } = useScript();
    await finalize(5);

    expect(mockSendMsg).toHaveBeenCalledWith({
      msg: expect.objectContaining({
        function_name: "finalize",
        args: "[5]",
      }),
      gasLimit: "auto",
      executorAddress: "dys2testaddr",
    });
  });

  it("throws on failed transaction", async () => {
    mockSendMsg.mockResolvedValue({
      success: false,
      scriptResponse: { exception: "Test error" },
    });

    const { depositBond } = useScript();
    await expect(depositBond("100")).rejects.toThrow("Test error");
  });

  it("uses rawLog when no exception", async () => {
    mockSendMsg.mockResolvedValue({
      success: false,
      rawSendMsgsResponse: { rawLog: "Raw error message" },
    });

    const { depositBond } = useScript();
    await expect(depositBond("100")).rejects.toThrow("Raw error message");
  });

  it("parses ValueError from rawLog", async () => {
    mockSendMsg.mockResolvedValue({
      success: false,
      rawSendMsgsResponse: {
        rawLog: `failed to execute message; message index: 0: {"cumsize":123,"exception":{"class":"DysRuntimeError","msg":"ValueError('commit deadline passed')"}}: script execution error`,
      },
    });

    const { commit } = useScript();
    await expect(commit(1, "hash")).rejects.toThrow("ValueError('commit deadline passed')");
  });

  it("extracts exception.msg from scriptResponse", async () => {
    mockSendMsg.mockResolvedValue({
      success: false,
      scriptResponse: {
        exception: { class: "ValueError", msg: "provider not registered" },
      },
    });

    const { commit } = useScript();
    await expect(commit(1, "hash")).rejects.toThrow("provider not registered");
  });

  it("builds correct message for setMinBond", async () => {
    const { setMinBond } = useScript();
    await setMinBond("500");

    expect(mockSendMsg).toHaveBeenCalledWith({
      msg: expect.objectContaining({
        function_name: "set_min_bond",
        args: '["500"]',
      }),
      gasLimit: "auto",
      executorAddress: "dys2testaddr",
    });
  });
});

