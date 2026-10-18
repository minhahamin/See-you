import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  // .env는 프로젝트 루트에 둔다 (VITE_ 접두사가 붙은 값만 브라우저에 노출된다)
  envDir: '..',
  // 개발 중에는 /api를 백엔드(uvicorn)로 넘긴다. 같은 출처로 보이므로 CORS 설정이 필요 없다.
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } },
});
