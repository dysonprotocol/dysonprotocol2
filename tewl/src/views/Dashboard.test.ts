import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import Dashboard from "./Dashboard.vue";

// Mock tewl lib
const mockGetState = vi.fn();
const mockGetActiveRequest = vi.fn();
const mockListRequests = vi.fn();
const mockListProviders = vi.fn();
const mockGetPendingRequests = vi.fn();

vi.mock("@/lib/tewl", () => ({
  getState: () => mockGetState(),
  getActiveRequest: () => mockGetActiveRequest(),
  listRequests: () => mockListRequests(),
  listProviders: () => mockListProviders(),
  getPendingRequests: () => mockGetPendingRequests(),
  getEffectiveStatus: (req: { status: string }) => req.status,
}));

describe("Dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading state initially", () => {
    mockGetState.mockImplementation(() => new Promise(() => {})); // never resolves
    mockGetActiveRequest.mockImplementation(() => new Promise(() => {}));
    mockListRequests.mockImplementation(() => new Promise(() => {}));
    mockListProviders.mockImplementation(() => new Promise(() => {}));
    mockGetPendingRequests.mockImplementation(() => new Promise(() => {}));

    const wrapper = mount(Dashboard);
    expect(wrapper.text()).toContain("Loading...");
  });

  it("renders stats after loading", async () => {
    mockGetState.mockResolvedValue({ next_request_id: 5, min_bond: "100", active_request_id: 3 });
    mockGetActiveRequest.mockResolvedValue({
      request_id: 3,
      prompt: "Test prompt",
      fee: "50",
      commits: {},
      reveals: {},
      status: "active",
    });
    mockListRequests.mockResolvedValue([]);
    mockListProviders.mockResolvedValue([
      { address: "p1", status: "active", bond: "100" },
      { address: "p2", status: "inactive", bond: "50" },
    ]);
    mockGetPendingRequests.mockResolvedValue([]);

    const wrapper = mount(Dashboard);
    await flushPromises();

    expect(wrapper.text()).toContain("Total Requests");
    expect(wrapper.text()).toContain("4"); // next_request_id - 1
    expect(wrapper.text()).toContain("Active Providers");
    expect(wrapper.text()).toContain("1"); // only 1 active
    expect(wrapper.text()).toContain("Min Bond");
    expect(wrapper.text()).toContain("100 udys");
  });

  it("renders request list", async () => {
    mockGetState.mockResolvedValue({ next_request_id: 3, min_bond: "100", active_request_id: null });
    mockGetActiveRequest.mockResolvedValue(null);
    mockListRequests.mockResolvedValue([
      { request_id: 1, prompt: "Request 1", status: "resolved" },
      { request_id: 2, prompt: "Request 2", status: "pending" },
    ]);
    mockListProviders.mockResolvedValue([]);
    mockGetPendingRequests.mockResolvedValue([
      { request_id: 2, prompt: "Request 2", fee: "10", status: "pending" },
    ]);

    const wrapper = mount(Dashboard);
    await flushPromises();

    expect(wrapper.text()).toContain("Request 1");
    expect(wrapper.text()).toContain("Request 2");
    expect(wrapper.text()).toContain("Pending Queue");
  });

  it("shows error state on failure", async () => {
    mockGetState.mockRejectedValue(new Error("Network error"));
    mockGetActiveRequest.mockRejectedValue(new Error("Network error"));
    mockListRequests.mockRejectedValue(new Error("Network error"));
    mockListProviders.mockRejectedValue(new Error("Network error"));
    mockGetPendingRequests.mockRejectedValue(new Error("Network error"));

    const wrapper = mount(Dashboard);
    await flushPromises();

    expect(wrapper.text()).toContain("Network error");
  });
});
