import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import RequestDetail from "./RequestDetail.vue";

// Mock vue-router
vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { id: "5" } }),
}));

// Mock useWallet
const mockWallet = ref({ address: "dys2testaddr" });
vi.mock("@/composables/useWallet", () => ({
  useWallet: () => ({
    wallet: mockWallet,
  }),
}));

// Mock useScript
const mockFinalize = vi.fn();
vi.mock("@/composables/useScript", () => ({
  useScript: () => ({
    finalize: mockFinalize,
  }),
}));

// Mock tewl lib
const mockGetRequest = vi.fn();

vi.mock("@/lib/tewl", () => ({
  getRequest: (...args: unknown[]) => mockGetRequest(...args),
  getEffectiveStatus: (req: { status: string }) => req?.status || "",
}));

describe("RequestDetail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWallet.value = { address: "dys2testaddr" };
  });

  it("renders loading state initially", () => {
    mockGetRequest.mockImplementation(() => new Promise(() => {}));
    const wrapper = mount(RequestDetail);
    expect(wrapper.text()).toContain("Loading...");
  });

  it("shows request not found", async () => {
    mockGetRequest.mockResolvedValue(null);
    const wrapper = mount(RequestDetail);
    await flushPromises();
    expect(wrapper.text()).toContain("Request not found");
  });

  it("renders request details", async () => {
    mockGetRequest.mockResolvedValue({
      request_id: 5,
      requester: "dys2requester",
      prompt: "What is the meaning of life?",
      response_schema: { type: "object" },
      scorer: "def scorer(r,s): return s",
      fee: "100",
      status: "active",
      commits: {},
      reveals: {},
      result: null,
      scores: {},
      commit_deadline: new Date(Date.now() + 60000).toISOString(),
      reveal_deadline: new Date(Date.now() + 120000).toISOString(),
    });

    const wrapper = mount(RequestDetail);
    await flushPromises();

    expect(wrapper.text()).toContain("Request #5");
    expect(wrapper.text()).toContain("What is the meaning of life?");
    expect(wrapper.text()).toContain("100 udys");
    expect(wrapper.text()).toContain("active");
  });

  it("shows provider participation with commits and reveals", async () => {
    mockGetRequest.mockResolvedValue({
      request_id: 5,
      requester: "dys2requester",
      prompt: "Test",
      response_schema: {},
      scorer: "",
      fee: "100",
      status: "revealing",
      commits: { "dys2provider1": { hash: "abc123def456" } },
      reveals: { "dys2provider1": { response: { answer: "42" } } },
      result: null,
      scores: {},
      commit_deadline: new Date(Date.now() - 60000).toISOString(),
      reveal_deadline: new Date(Date.now() + 60000).toISOString(),
    });

    const wrapper = mount(RequestDetail);
    await flushPromises();

    expect(wrapper.text()).toContain("Providers (1)");
    expect(wrapper.text()).toContain("✓ commit");
    expect(wrapper.text()).toContain("✓ reveal");
  });

  it("shows result and scores when resolved", async () => {
    mockGetRequest.mockResolvedValue({
      request_id: 5,
      requester: "dys2requester",
      prompt: "Test",
      response_schema: {},
      scorer: "",
      fee: "100",
      status: "resolved",
      commits: { "dys2provider1": { hash: "abc" } },
      reveals: { "dys2provider1": { response: { answer: "42" } } },
      result: { answer: "The answer is 42" },
      scores: { "dys2provider1": 1.0 },
      commit_deadline: new Date(Date.now() - 120000).toISOString(),
      reveal_deadline: new Date(Date.now() - 60000).toISOString(),
    });

    const wrapper = mount(RequestDetail);
    await flushPromises();

    expect(wrapper.text()).toContain("Result");
    expect(wrapper.text()).toContain("The answer is 42");
    expect(wrapper.text()).toContain("1.00"); // score displayed inline
  });
});
