import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
const privateData=fileURLToPath(new URL('./data',import.meta.url));
export default defineConfig({server:{host:'127.0.0.1',watch:{ignored:['**/.venv/**',`${privateData}/**`,'**/backend/**','**/dist/**','**/docs/**','**/scripts/**','**/contracts/**','**/examples/**','**/tests/**']},proxy:{'/api':{target:'http://127.0.0.1:8001',changeOrigin:true}}}});
