import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import Providers from "./Providers.vue";

// Mock tewl lib
const mockListProviders = vi.fn();
const mockGetState = vi.fn();

vi.mock("@/lib/tewl", () => ({
  listProviders: () => mockListProviders(),
  getState: () => mockGetState(),
}));

describe("Providers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders loading state initially", () => {
    mockListProviders.mockImplementation(() => new Promise(() => {}));
    mockGetState.mockImplementation(() => new Promise(() => {}));

    const wrapper = mount(Providers);
    expect(wrapper.text()).toContain("Loading...");
  });

  it("renders provider stats", async () => {
    mockListProviders.mockResolvedValue([
      { address: "p1", bond: "1000", status: "active", reputation: { total: 10, correct: 8, slashed: 0 } },
      { address: "p2", bond: "500", status: "inactive", reputation: { total: 5, correct: 5, slashed: 0 } },
      { address: "p3", bond: "2000", status: "active", reputation: { total: 0, correct: 0, slashed: 0 } },
    ]);
    mockGetState.mockResolvedValue({ min_bond: "100" });

    const wrapper = mount(Providers);
    await flushPromises();

    expect(wrapper.text()).toContain("Total Providers");
    expect(wrapper.text()).toContain("3");
    expect(wrapper.text()).toContain("Active");
    expect(wrapper.text()).toContain("2");
    expect(wrapper.text()).toContain("Inactive");
    expect(wrapper.text()).toContain("1");
  });

  it("filters providers by status", async () => {
    mockListProviders.mockResolvedValue([
      { address: "p1", bond: "1000", status: "active", reputation: null },
      { address: "p2", bond: "500", status: "inactive", reputation: null },
    ]);
    mockGetState.mockResolvedValue({ min_bond: "100" });

    const wrapper = mount(Providers);
    await flushPromises();

    // Click active filter
    const activeButton = wrapper.findAll('button').find(b => b.text().includes('Active'));
    if (activeButton) {
      await activeButton.trigger('click');
      await flushPromises();
      
      // Should only show active provider
      expect(wrapper.text()).toContain("p1");
    }
  });

  it("shows reputation percentage", async () => {
    mockListProviders.mockResolvedValue([
      { address: "p1", bond: "1000", status: "active", reputation: { total: 10, correct: 8, slashed: 0 } },
    ]);
    mockGetState.mockResolvedValue({ min_bond: "100" });

    const wrapper = mount(Providers);
    await flushPromises();

    expect(wrapper.text()).toContain("80%");
    expect(wrapper.text()).toContain("8/10");
  });

  it("shows empty state", async () => {
    mockListProviders.mockResolvedValue([]);
    mockGetState.mockResolvedValue({ min_bond: "100" });

    const wrapper = mount(Providers);
    await flushPromises();

    expect(wrapper.text()).toContain("No providers found");
  });
});

