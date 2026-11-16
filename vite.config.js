import {defineConfig} from 'vite';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {resolve} from 'node:path';

const privateData=fileURLToPath(new URL('./data',import.meta.url));

// macOS cp can clone large terrain assets on APFS. Build output remains a
// self-contained directory with independent, writable files.
function clonePublicAssets() {
  let publicDir;
  return {
    name:'clavius-public-assets',
    apply:'build',
    config(config) {
      if(config.publicDir===false || config.build?.copyPublicDir===false)return;
      publicDir=resolve(config.root ?? '.',config.publicDir ?? 'public');
      return {build:{copyPublicDir:false}};
    },
    writeBundle(options) {
      if(publicDir && existsSync(publicDir) && options.dir) {
        execFileSync('/bin/cp',['-cR',publicDir+'/.',options.dir]);
      }
    }
  };
}

export default defineConfig({
  optimizeDeps:{include:['react','react-dom/client','lucide-react','recharts']},
  plugins:process.platform==='darwin'?[clonePublicAssets()]:[],
  server:{host:'127.0.0.1',watch:{ignored:['**/.venv/**',privateData+'/**','**/backend/**','**/dist/**','**/docs/**','**/scripts/**','**/contracts/**','**/examples/**','**/tests/**']},proxy:{'/api':{target:'http://127.0.0.1:8001',changeOrigin:true}}}
});
