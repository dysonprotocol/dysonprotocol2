/// <reference types="vitest" />
import { defineConfig, loadEnv } from "vite";
import { cwd, env as nodeEnv } from "node:process";
import { resolve } from "path";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, cwd(), "");
  const proxyTarget =
    env.DYSONPROTOCOL_API ||
    env.VITE_DYSONPROTOCOL_API ||
    nodeEnv.DYSONPROTOCOL_API ||
    "http://localhost:1317";
  const wsProxyTarget = proxyTarget.replace(/^http/, "ws");

  console.log("TEWL UI proxy target:", proxyTarget);

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
      },
    },
    test: {
      environment: "jsdom",
      include: ["src/**/*.{test,spec}.{js,ts,vue}"],
      setupFiles: ["./src/test-setup.ts"],
      coverage: {
        provider: "v8",
        reporter: ["text", "html"],
        include: ["src/**/*.{ts,vue}"],
        exclude: ["src/**/*.test.ts", "src/**/*.d.ts", "src/main.ts"],
      },
      globals: true,
    },
    server: {
      port: 5179,
      proxy: {
        "/cosmos": {
          target: proxyTarget,
          changeOrigin: true,
          secure: false,
          headers: { Connection: "keep-alive" },
          timeout: 60000,
          proxyTimeout: 60000,
        },
        "/dysonprotocol": {
          target: proxyTarget,
          changeOrigin: true,
          secure: false,
          headers: { Connection: "keep-alive" },
          timeout: 60000,
          proxyTimeout: 60000,
        },
        "/ibc": {
          target: proxyTarget,
          changeOrigin: true,
          secure: false,
          headers: { Connection: "keep-alive" },
          timeout: 60000,
          proxyTimeout: 60000,
        },
        "/rpc/websocket": {
          target: wsProxyTarget,
          changeOrigin: true,
          secure: false,
          ws: true,
        },
        "/rpc": {
          target: proxyTarget,
          changeOrigin: false,
          secure: false,
          headers: { Connection: "keep-alive" },
          timeout: 60000,
          proxyTimeout: 60000,
        },
      },
    },
  };
});
