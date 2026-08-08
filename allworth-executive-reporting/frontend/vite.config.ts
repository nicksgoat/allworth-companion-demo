import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  // Tailwind serves ONLY the Executive Brief (src/brief): its stylesheet
  // limits class scanning via @source and ships no preflight, so it cannot
  // affect other tools' styles.
  plugins: [react(), tailwindcss()],
  build: {
    // Split the heavyweight vendor libraries into stable, cacheable chunks so
    // a app-code deploy doesn't invalidate the MUI/recharts downloads and the
    // first paint of non-planning pages doesn't pay for chart libraries.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          mui: ['@mui/material', '@mui/icons-material'],
          charts: ['recharts'],
        },
      },
    },
  },
  server: {
    proxy: {
      '/fee-calculator/api': 'http://127.0.0.1:5000',
      '/pipeline-review/api': 'http://127.0.0.1:5000',
      '/executive-report/api': 'http://127.0.0.1:5000',
      '/brief/api': 'http://127.0.0.1:5000',
      '/home': 'http://127.0.0.1:5000',
      '/jarvis': 'http://127.0.0.1:5000',
      '/catalog': 'http://127.0.0.1:5000',
      '/api': 'http://127.0.0.1:5000',
    },
  },
})
