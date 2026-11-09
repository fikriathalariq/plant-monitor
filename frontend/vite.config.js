import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  build: {
    // Jangan hapus chunk lama saat build baru agar tab browser pengguna yang terbuka lama
    // tidak mendadak error 404 saat melakukan lazy-loading menu baru.
    emptyOutDir: false,
  },
  server: {
    // Port 8002 dipakai untuk staging pengganti Django SSR di port 8000
    // Port 8003: engineer workspace dev profile (npm run dev:engineer)
    port: parseInt(process.env.VITE_PORT || '8002', 10),
    host: true,
    allowedHosts: true,
  }
})
