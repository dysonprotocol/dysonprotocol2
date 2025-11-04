import { ConfigEnv, defineConfig, loadEnv } from "vite";
import { cwd, env as nodeEnv } from "node:process";
import { resolve, dirname } from "path";



export default defineConfig(({ mode }) => {

    const env = loadEnv(mode, cwd(), "");
    const proxyTarget =
        env.DYSONPROTOCOL_API ||
        env.VITE_DYSONPROTOCOL_API ||
        nodeEnv.DYSONPROTOCOL_API ||
        "http://localhost:1417";
    const wsProxyTarget = proxyTarget.replace(/^http/, "ws");

    console.log("vite2 proxyTarget", proxyTarget);
    return {
        resolve: {
            alias: {
                "@": resolve(__dirname, "src"),
                "@dyson/libp2p": resolve(__dirname, "src/sdk"),
            },
        },
        define: {
            "process.env.NODE_ENV": '"production"',
            "process.env": {},
            __DEV__: "false",
            __VUE_PROD_DEVTOOLS__: "false",
            __VUE_OPTIONS_API__: "true",
        },
        optimizeDeps: {
            esbuildOptions: {
                target: "es2020",
                define: {},
            },
        },

        server: {
            port: 5173,

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
                "/swagger": {
                    target: proxyTarget,
                    changeOrigin: false,
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
                "/host.json": {
                    target: proxyTarget,
                    changeOrigin: false,
                    secure: false,
                },
                "/redirect-to-dwapp": {
                    target: proxyTarget,
                    changeOrigin: true,
                    secure: false,
                },
                "/libp2p": {
                    target: proxyTarget,
                    changeOrigin: true,
                    secure: false,
                    headers: { Connection: "keep-alive" },

                },
            }
        }
    }
})

