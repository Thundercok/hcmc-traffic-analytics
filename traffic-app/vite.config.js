import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/hcmc-camera': {
        target: 'https://giaothong.hochiminhcity.gov.vn',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path.replace(/^\/hcmc-camera/, ''),
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('Referer', 'https://giaothong.hochiminhcity.gov.vn/');
            proxyReq.setHeader('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36');
          });
          proxy.on('error', (err, req, res) => {
            if (!res.headersSent) {
              res.writeHead(504, { 'Content-Type': 'text/plain' });
            }
            res.end('Camera Server Timeout');
          });
        }
      },
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  },
  define: {
    'import.meta.env.VITE_API_URL': JSON.stringify(process.env.VITE_API_URL || '/api'),
  }
})
