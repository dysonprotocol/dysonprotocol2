import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import CreateRequest from "./CreateRequest.vue";

// Mock vue-router
const mockPush = vi.fn();
vi.mock("vue-router", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Mock useWallet - provide a connected wallet
const mockWallet = ref({ address: "dys2testaddr" });
vi.mock("@/composables/useWallet", () => ({
  useWallet: () => ({
    wallet: mockWallet,
  }),
}));

// Mock useScript
const mockCreateRequest = vi.fn();
vi.mock("@/composables/useScript", () => ({
  useScript: () => ({
    createRequest: mockCreateRequest,
  }),
}));

// Mock tewl lib
vi.mock("@/lib/tewl", () => ({
  getScriptAddress: () => "dys2testscript",
  getBalance: vi.fn().mockResolvedValue("1000000"),
}));

describe("CreateRequest", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWallet.value = { address: "dys2testaddr" };
  });

  it("renders the form when wallet connected", async () => {
    const wrapper = mount(CreateRequest);
    await flushPromises();

    expect(wrapper.text()).toContain("Create Request");
    expect(wrapper.text()).toContain("Prompt");
    expect(wrapper.text()).toContain("Response Schema");
    expect(wrapper.text()).toContain("Scorer");
    expect(wrapper.text()).toContain("Fee");
  });

  it("shows connect wallet when not connected", async () => {
    mockWallet.value = { address: null } as any;
    const wrapper = mount(CreateRequest);
    await flushPromises();

    expect(wrapper.text()).toContain("Connect wallet");
  });

  it("has default prompt value", async () => {
    const wrapper = mount(CreateRequest);
    await flushPromises();

    const promptInput = wrapper.find('input[placeholder*="New York"]');
    expect(promptInput.exists()).toBe(true);
  });

  it("shows error on failed transaction", async () => {
    mockCreateRequest.mockRejectedValue(new Error("Test error"));

    const wrapper = mount(CreateRequest);
    await flushPromises();

    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Test error");
  });

  it("redirects on success", async () => {
    mockCreateRequest.mockResolvedValue({ success: true });

    const wrapper = mount(CreateRequest);
    await flushPromises();

    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(mockPush).toHaveBeenCalledWith("/");
  });
});
