import { config } from "@vue/test-utils";
import { vi } from "vitest";

// Test mnemonic - DO NOT use in production
export const TEST_MNEMONIC = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about";
// Derived address with dys2 prefix
export const TEST_ADDRESS = "dys219rl4cm2hmr8afy4kldpxz3fka4jguq0akskt0x";

// Mock fetch globally
global.fetch = vi.fn();

// Mock crypto.getRandomValues
Object.defineProperty(global, "crypto", {
  value: {
    getRandomValues: (arr: Uint8Array) => {
      for (let i = 0; i < arr.length; i++) {
        arr[i] = Math.floor(Math.random() * 256);
      }
      return arr;
    },
  },
});

// Stub router-link globally
config.global.stubs = {
  "router-link": {
    template: '<a :href="to"><slot /></a>',
    props: ["to"],
  },
};

