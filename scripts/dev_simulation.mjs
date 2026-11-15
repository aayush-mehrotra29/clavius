import { spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
const cwd=resolve(import.meta.dirname,'..');
if(!existsSync(resolve(cwd,'.venv/bin/python'))){console.error('Simulation dependencies are missing. Run: uv venv .venv && uv pip install --python .venv/bin/python -r requirements-simulation.txt');process.exit(1);}
const children=[];
const localWorker={};
const workerEnvPath=resolve(cwd,'data/runtime/gazebo-local.env');
if(existsSync(workerEnvPath))for(const line of readFileSync(workerEnvPath,'utf8').split(/\r?\n/)){
 const separator=line.indexOf('=');const key=line.slice(0,separator);
 if(['CLAVIUS_GAZEBO_URL','CLAVIUS_GAZEBO_TOKEN'].includes(key))localWorker[key]=line.slice(separator+1);
}
async function available(url){try{return (await fetch(url,{signal:AbortSignal.timeout(3000)})).ok;}catch{return false;}}
if(!await available('http://127.0.0.1:8001/api/v1/health'))children.push(spawn(resolve(cwd,'.venv/bin/python'),['-m','uvicorn','clavius.api:app','--host','127.0.0.1','--port','8001'],{cwd,stdio:'inherit',env:{...localWorker,...process.env,PYTHONPATH:resolve(cwd,'backend'),OPENBLAS_NUM_THREADS:'1'}}));
if(!await available('http://127.0.0.1:5173'))children.push(spawn(process.execPath,[resolve(cwd,'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','5173'],{cwd,stdio:'inherit'}));
console.log('Clavius simulation: http://127.0.0.1:5173/app/simulation');
for(const child of children)child.on('exit',code=>{if(code)console.error(`Service exited with code ${code}`);});
const shutdown=()=>{for(const child of children)child.kill('SIGTERM');process.exit(0);};
process.on('SIGINT',shutdown);process.on('SIGTERM',shutdown);
if(!children.length)console.log('Existing local services are already running.');
