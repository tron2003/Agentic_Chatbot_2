import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // In development the UI runs on :3000 and proxies API calls to the backend,
  // so no CORS setup is needed. In production FastAPI serves the built files.
  const backend = env.VITE_DEV_BACKEND || 'http://127.0.0.1:8001';

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { '@': path.resolve(import.meta.dirname, './src') },
    },
    server: {
      port: 3000,
      host: '0.0.0.0',
      proxy: {
        '/api': { target: backend, changeOrigin: true },
        '/health': { target: backend, changeOrigin: true },
        '/ready': { target: backend, changeOrigin: true },
      },
    },
    build: {
      target: 'es2022',
      sourcemap: false,
      chunkSizeWarningLimit: 700,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('highlight.js') || id.includes('lowlight')) return 'highlight';
            if (/react-markdown|remark|rehype|micromark|mdast|hast|unified|vfile/.test(id)) return 'markdown';
            if (id.includes('node_modules/motion') || id.includes('framer-motion')) return 'motion';
          },
        },
      },
    },
  };
});
