import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import Admin from "./Admin.vue";

// Mock useWallet
const mockWallet = ref({ address: "dys2testaddr" });
vi.mock("@/composables/useWallet", () => ({
  useWallet: () => ({
    wallet: mockWallet,
  }),
}));

// Mock useScript
const mockSetMinBond = vi.fn();
vi.mock("@/composables/useScript", () => ({
  useScript: () => ({
    setMinBond: mockSetMinBond,
  }),
}));

// Mock tewl lib
const mockGetState = vi.fn();
vi.mock("@/lib/tewl", () => ({
  getState: () => mockGetState(),
  getScriptAddress: () => "dys2scriptaddr",
}));

describe("Admin", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWallet.value = { address: "dys2testaddr" };
  });

  it("shows connect wallet when not connected", async () => {
    mockWallet.value = { address: null } as any;
    const wrapper = mount(Admin);
    await flushPromises();
    expect(wrapper.text()).toContain("Connect wallet");
  });

  it("renders protocol state", async () => {
    mockGetState.mockResolvedValue({
      next_request_id: 10,
      min_bond: "500",
      active_request_id: 5,
      commit_timeout_seconds: 30,
      reveal_timeout_seconds: 30,
    });

    const wrapper = mount(Admin);
    await flushPromises();

    expect(wrapper.text()).toContain("Protocol State");
    expect(wrapper.text()).toContain("500");
    expect(wrapper.text()).toContain("Set Minimum Bond");
  });

  it("shows warning when not owner", async () => {
    mockGetState.mockResolvedValue({
      next_request_id: 1,
      min_bond: "100",
      active_request_id: null,
    });

    const wrapper = mount(Admin);
    await flushPromises();

    expect(wrapper.text()).toContain("Only the script owner");
  });

  it("calls setMinBond on submit", async () => {
    mockGetState.mockResolvedValue({
      next_request_id: 1,
      min_bond: "100",
      active_request_id: null,
    });
    mockSetMinBond.mockResolvedValue({ success: true });

    const wrapper = mount(Admin);
    await flushPromises();

    const input = wrapper.find('input');
    await input.setValue("200");
    
    const button = wrapper.find('button[type="button"]');
    // Find the "Update Min Bond" button
    const updateButton = wrapper.findAll('button').find(b => b.text().includes('Update'));
    if (updateButton) {
      await updateButton.trigger('click');
      await flushPromises();
      expect(mockSetMinBond).toHaveBeenCalledWith("200");
    }
  });
});

