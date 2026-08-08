import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  // Tailwind serves ONLY the Executive Brief (src/brief): its stylesheet
  // limits class scanning via @source and ships no preflight, so it cannot
  // affect other tools' styles.
  plugins: [react(), tailwindcss()],
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
