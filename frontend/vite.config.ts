import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiProxyTarget = process.env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8788';

export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      usePolling: process.env.CHOKIDAR_USEPOLLING === 'true'
    },
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true
      }
    }
  }
});
