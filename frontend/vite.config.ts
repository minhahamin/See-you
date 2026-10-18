import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  // .env는 프로젝트 루트에 둔다 (VITE_ 접두사가 붙은 값만 브라우저에 노출된다)
  envDir: '..',
  server: { port: 5173 },
});
