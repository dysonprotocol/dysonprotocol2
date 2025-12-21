import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import Provider from "./Provider.vue";

// Mock useWallet
const mockWallet = ref({ address: "dys2testprovider" });
vi.mock("@/composables/useWallet", () => ({
  useWallet: () => ({
    wallet: mockWallet,
  }),
}));

// Mock useScript
const mockDepositBond = vi.fn();
const mockWithdrawBond = vi.fn();
const mockCommit = vi.fn();
const mockReveal = vi.fn();
const mockFinalize = vi.fn();

vi.mock("@/composables/useScript", () => ({
  useScript: () => ({
    depositBond: mockDepositBond,
    withdrawBond: mockWithdrawBond,
    commit: mockCommit,
    reveal: mockReveal,
    finalize: mockFinalize,
  }),
}));

// Mock tewl lib
const mockGetProvider = vi.fn();
const mockGetActiveRequest = vi.fn();
const mockGetState = vi.fn();

vi.mock("@/lib/tewl", () => ({
  getProvider: (...args: unknown[]) => mockGetProvider(...args),
  getActiveRequest: (...args: unknown[]) => mockGetActiveRequest(...args),
  getState: (...args: unknown[]) => mockGetState(...args),
  computeCommitHash: vi.fn().mockReturnValue("abc123hash"),
  generateSalt: vi.fn().mockReturnValue("randomsalt"),
  getEffectiveStatus: vi.fn((req) => req?.status || ""),
}));

const defaultState = {
  next_request_id: 1,
  min_bond: "100",
  active_request_id: null,
  commit_timeout_seconds: 30,
  reveal_timeout_seconds: 30,
};

const activeProvider = {
  address: "dys2testprovider",
  bond: "1000",
  reputation: { total: 10, correct: 8, slashed: 0 },
  status: "active",
  registered_at: 100,
};

const activeRequest = {
  request_id: 5,
  requester: "dys2...",
  prompt: "What is 2+2?",
  response_schema: { type: "object" },
  scorer: "",
  fee: "100",
  callback_script: "",
  callback_fn: "",
  created_at: 100,
  status: "active",
  commits: {},
  reveals: {},
  result: null,
  scores: {},
  commit_deadline: new Date(Date.now() + 60000).toISOString(),
  reveal_deadline: new Date(Date.now() + 120000).toISOString(),
};

describe("Provider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWallet.value = { address: "dys2testprovider" };
    localStorage.clear();
    mockDepositBond.mockResolvedValue({ success: true });
    mockWithdrawBond.mockResolvedValue({ success: true });
    mockCommit.mockResolvedValue({ success: true });
    mockReveal.mockResolvedValue({ success: true });
    mockFinalize.mockResolvedValue({ success: true });
  });

  it("shows connect wallet message when no wallet", async () => {
    mockWallet.value = { address: null } as any;
    const wrapper = mount(Provider);
    await flushPromises();
    expect(wrapper.text()).toContain("Connect wallet");
  });

  it("renders provider status when registered", async () => {
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(null);
    mockGetState.mockResolvedValue(defaultState);

    const wrapper = mount(Provider);
    await flushPromises();

    expect(wrapper.text()).toContain("Your Status");
    expect(wrapper.text()).toContain("1000 udys");
    expect(wrapper.text()).toContain("active");
  });

  it("shows not registered message when no provider", async () => {
    mockGetProvider.mockResolvedValue(null);
    mockGetActiveRequest.mockResolvedValue(null);
    mockGetState.mockResolvedValue(defaultState);

    const wrapper = mount(Provider);
    await flushPromises();

    expect(wrapper.text()).toContain("Not registered");
  });

  it("shows active request when available", async () => {
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(activeRequest);
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });

    const wrapper = mount(Provider);
    await flushPromises();

    expect(wrapper.text()).toContain("Request #5");
    expect(wrapper.text()).toContain("What is 2+2?");
  });

  it("shows no active request message", async () => {
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(null);
    mockGetState.mockResolvedValue(defaultState);

    const wrapper = mount(Provider);
    await flushPromises();

    expect(wrapper.text()).toContain("No active request");
  });

  // Bond management tests
  it("calls depositBond when deposit button clicked", async () => {
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(null);
    mockGetState.mockResolvedValue(defaultState);

    const wrapper = mount(Provider);
    await flushPromises();

    const inputs = wrapper.findAll('input');
    const depositInput = inputs[0];
    await depositInput.setValue("5000");

    const depositButton = wrapper.findAll('button').find(b => b.text() === 'Deposit');
    await depositButton?.trigger('click');
    await flushPromises();

    expect(mockDepositBond).toHaveBeenCalledWith("5000");
  });

  it("calls withdrawBond when withdraw button clicked", async () => {
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(null);
    mockGetState.mockResolvedValue(defaultState);

    const wrapper = mount(Provider);
    await flushPromises();

    const inputs = wrapper.findAll('input');
    const withdrawInput = inputs[1];
    await withdrawInput.setValue("500");

    const withdrawButton = wrapper.findAll('button').find(b => b.text() === 'Withdraw');
    await withdrawButton?.trigger('click');
    await flushPromises();

    expect(mockWithdrawBond).toHaveBeenCalledWith("500");
  });

  it("shows error when deposit fails", async () => {
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(null);
    mockGetState.mockResolvedValue(defaultState);
    mockDepositBond.mockRejectedValue(new Error("Insufficient funds"));

    const wrapper = mount(Provider);
    await flushPromises();

    const inputs = wrapper.findAll('input');
    await inputs[0].setValue("5000");

    const depositButton = wrapper.findAll('button').find(b => b.text() === 'Deposit');
    await depositButton?.trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain("Insufficient funds");
  });

  // Commit tests
  it("shows commit hash when response entered", async () => {
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(activeRequest);
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });

    const wrapper = mount(Provider);
    await flushPromises();

    const textarea = wrapper.find('textarea');
    await textarea.setValue('{"answer": "4"}');
    await flushPromises();

    expect(wrapper.text()).toContain("Commit Hash");
    expect(wrapper.text()).toContain("abc123hash");
  });

  it("calls commit when submit commit clicked", async () => {
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(activeRequest);
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });

    const wrapper = mount(Provider);
    await flushPromises();

    const textarea = wrapper.find('textarea');
    await textarea.setValue('{"answer": "4"}');
    await flushPromises();

    const commitButton = wrapper.findAll('button').find(b => b.text() === 'Submit Commit');
    await commitButton?.trigger('click');
    await flushPromises();

    expect(mockCommit).toHaveBeenCalledWith(5, "abc123hash");
    expect(localStorage.getItem('tewl_salt_5')).toBe('randomsalt');
    expect(localStorage.getItem('tewl_response_5')).toBe('{"answer": "4"}');
  });

  // Reveal tests
  it("shows reveal button in revealing phase", async () => {
    const revealingRequest = {
      ...activeRequest,
      status: "revealing",
      commits: { "dys2testprovider": { hash: "abc123" } },
    };
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(revealingRequest);
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });

    // Mock getEffectiveStatus to return revealing
    const tewl = await import("@/lib/tewl");
    vi.mocked(tewl.getEffectiveStatus).mockReturnValue("revealing");

    const wrapper = mount(Provider);
    await flushPromises();

    expect(wrapper.text()).toContain("Submit Reveal");
  });

  it("calls reveal when submit reveal clicked", async () => {
    const revealingRequest = {
      ...activeRequest,
      status: "revealing",
      commits: { "dys2testprovider": { hash: "abc123hash" } },
    };
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(revealingRequest);
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });

    const tewl = await import("@/lib/tewl");
    vi.mocked(tewl.getEffectiveStatus).mockReturnValue("revealing");
    // Mock computeCommitHash to return the same hash as stored (so button is enabled)
    vi.mocked(tewl.computeCommitHash).mockReturnValue("abc123hash");

    const wrapper = mount(Provider);
    await flushPromises();

    const textarea = wrapper.find('textarea');
    await textarea.setValue('{"answer": "4"}');
    await flushPromises();

    const revealButton = wrapper.findAll('button').find(b => b.text() === 'Submit Reveal');
    await revealButton?.trigger('click');
    await flushPromises();

    expect(mockReveal).toHaveBeenCalledWith(5, { answer: "4" }, "randomsalt");
  });

  it("successful reveal flow - auto-loads saved commit data and reveals", async () => {
    // Setup: User previously committed, salt/response saved in localStorage
    localStorage.setItem('tewl_salt_5', 'mysavedsalt123');
    localStorage.setItem('tewl_response_5', '{"answer": "42"}');

    const revealingRequest = {
      ...activeRequest,
      status: "revealing",
      commits: { "dys2testprovider": { hash: "abc123hash", timestamp: new Date().toISOString() } },
      reveals: {},
    };

    // After successful reveal, the request will have our reveal
    const revealedRequest = {
      ...revealingRequest,
      reveals: { 
        "dys2testprovider": { 
          response: { answer: "42" }, 
          timestamp: new Date().toISOString(),
          valid: true 
        } 
      },
    };

    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest
      .mockResolvedValueOnce(revealingRequest)  // Initial load
      .mockResolvedValueOnce(revealedRequest);   // After reveal
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });
    mockReveal.mockResolvedValue({ success: true });

    const tewl = await import("@/lib/tewl");
    vi.mocked(tewl.getEffectiveStatus).mockReturnValue("revealing");
    // Mock computeCommitHash to return the stored hash (simulating match)
    vi.mocked(tewl.computeCommitHash).mockReturnValue("abc123hash");

    const wrapper = mount(Provider);
    await flushPromises();

    // 1. Data should be auto-loaded because user has committed
    const textarea = wrapper.find('textarea');
    expect((textarea.element as HTMLTextAreaElement).value).toBe('{"answer": "42"}');

    // 2. Submit reveal
    const revealButton = wrapper.findAll('button').find(b => b.text() === 'Submit Reveal');
    expect(revealButton?.exists()).toBe(true);
    
    await revealButton?.trigger('click');
    await flushPromises();

    // 3. Verify reveal was called with correct params
    expect(mockReveal).toHaveBeenCalledWith(5, { answer: "42" }, "mysavedsalt123");

    // 4. Verify data was reloaded after reveal
    expect(mockGetActiveRequest).toHaveBeenCalledTimes(2);
  });

  it("shows revealed status after successful reveal", async () => {
    const revealedRequest = {
      ...activeRequest,
      status: "revealing",
      commits: { "dys2testprovider": { hash: "abc123" } },
      reveals: { "dys2testprovider": { response: { answer: "42" }, valid: true } },
    };

    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(revealedRequest);
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });

    const tewl = await import("@/lib/tewl");
    vi.mocked(tewl.getEffectiveStatus).mockReturnValue("revealing");

    const wrapper = mount(Provider);
    await flushPromises();

    // Should show "Revealed" checkmark, not reveal button
    expect(wrapper.text()).toContain("✓ Revealed");
    expect(wrapper.text()).not.toContain("Submit Reveal");
  });

  // Finalize tests
  it("shows finalize button in finalizing phase", async () => {
    const finalizingRequest = {
      ...activeRequest,
      status: "finalizing",
    };
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(finalizingRequest);
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });

    const tewl = await import("@/lib/tewl");
    vi.mocked(tewl.getEffectiveStatus).mockReturnValue("finalizing");

    const wrapper = mount(Provider);
    await flushPromises();

    expect(wrapper.text()).toContain("Finalize");
  });

  it("calls finalize when finalize button clicked", async () => {
    const finalizingRequest = {
      ...activeRequest,
      status: "finalizing",
    };
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(finalizingRequest);
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });

    const tewl = await import("@/lib/tewl");
    vi.mocked(tewl.getEffectiveStatus).mockReturnValue("finalizing");

    const wrapper = mount(Provider);
    await flushPromises();

    const finalizeButton = wrapper.findAll('button').find(b => b.text() === 'Finalize');
    await finalizeButton?.trigger('click');
    await flushPromises();

    expect(mockFinalize).toHaveBeenCalledWith(5);
  });

  // Load saved response
  it("loads saved response from localStorage on click", async () => {
    localStorage.setItem('tewl_salt_5', 'savedsalt123');
    localStorage.setItem('tewl_response_5', '{"saved": "response"}');

    // Request where user has committed (so load saved button appears)
    const committedRequest = {
      ...activeRequest,
      commits: { "dys2testprovider": { hash: "abc123" } },
    };

    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(committedRequest);
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });

    const wrapper = mount(Provider);
    await flushPromises();

    // Should auto-load because user has committed
    const textarea = wrapper.find('textarea');
    expect((textarea.element as HTMLTextAreaElement).value).toBe('{"saved": "response"}');
  });

  it("auto-loads saved data when user has committed", async () => {
    localStorage.setItem('tewl_salt_5', 'autosalt');
    localStorage.setItem('tewl_response_5', '{"auto": "loaded"}');

    const committedRequest = {
      ...activeRequest,
      commits: { "dys2testprovider": { hash: "abc123" } },
    };

    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(committedRequest);
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });

    const wrapper = mount(Provider);
    await flushPromises();

    const textarea = wrapper.find('textarea');
    expect((textarea.element as HTMLTextAreaElement).value).toBe('{"auto": "loaded"}');
  });

  // Inactive provider warning
  it("shows inactive warning when provider status is inactive", async () => {
    const inactiveProvider = { ...activeProvider, status: "inactive", bond: "50" };
    mockGetProvider.mockResolvedValue(inactiveProvider);
    mockGetActiveRequest.mockResolvedValue(null);
    mockGetState.mockResolvedValue(defaultState);

    const wrapper = mount(Provider);
    await flushPromises();

    expect(wrapper.text()).toContain("You need at least");
    expect(wrapper.text()).toContain("100 udys");
  });

  // Regenerate salt
  it("regenerates salt when clicked", async () => {
    mockGetProvider.mockResolvedValue(activeProvider);
    mockGetActiveRequest.mockResolvedValue(activeRequest);
    mockGetState.mockResolvedValue({ ...defaultState, active_request_id: 5 });

    const wrapper = mount(Provider);
    await flushPromises();

    const regenerateButton = wrapper.findAll('button').find(b => b.text() === 'regenerate');
    await regenerateButton?.trigger('click');
    await flushPromises();

    // Salt should have been regenerated (generateSalt was called)
    const tewl = await import("@/lib/tewl");
    expect(tewl.generateSalt).toHaveBeenCalled();
  });
});
