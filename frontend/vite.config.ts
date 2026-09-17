import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ mode }) => {
  const backendTarget = loadEnv(mode, ".", "").VITE_PROXY_TARGET || "http://127.0.0.1:8023";
  return {
    plugins: [vue()],
    server: {
      port: 4021,
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: false,
        },
        "/uploads": {
          target: backendTarget,
          changeOrigin: false,
        },
      },
    },
  };
});
