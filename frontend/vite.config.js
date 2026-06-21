import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      // Sidecar: local detection pipeline on localhost:8765
      '/detect': 'http://127.0.0.1:8765',
      '/ws/audio': {
        target: 'ws://127.0.0.1:8765',
        ws: true,
      },
    },
  },
})
