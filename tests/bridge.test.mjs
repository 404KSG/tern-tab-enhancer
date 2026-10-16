import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,mkdtempSync,mkdirSync,readFileSync,rmSync,statSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

const source=readFileSync(new URL('../pi/bridge.ts',import.meta.url),'utf8');
const bridge=(await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))).default;
function fixture(fn, mode='tui') {
  const root=mkdtempSync(join(tmpdir(),'tte-bridge-unit-'));
  const keys=['TERN_PANE','TERN_PANE_SOCKET','TERN_CONFIG_DIR'];
  const before=Object.fromEntries(keys.map(k=>[k,process.env[k]]));
  process.env.TERN_PANE='123';process.env.TERN_PANE_SOCKET=join(root,'pane.sock');process.env.TERN_CONFIG_DIR=root;
  mkdirSync(join(root,'plugins/tern-tab-enhancer'),{recursive:true});
  writeFileSync(join(root,'plugins/tern-tab-enhancer/plugin.toml'),'schema = 1\n');
  const handlers=new Map();const api={on:(name,fn)=>handlers.set(name,fn)};
  bridge(api);
  const ctx={mode};const path=join(root,'plugin-data/tern-tab-enhancer/bridge/123.json');
  const state=()=>JSON.parse(readFileSync(path,'utf8'));
  const emit=(name,event={})=>handlers.get(name)?.(event,ctx);
  try {fn({root,path,state,emit,handlers,ctx,api});}
  finally {
    emit('session_shutdown');
    for(const key of keys) if(before[key]===undefined) delete process.env[key];else process.env[key]=before[key];
    rmSync(root,{recursive:true,force:true});
  }
}

test('bridge: idle, work, blocking dialog, restored work and settled completion',()=>fixture(({state,emit,path})=>{
  emit('session_start');assert.equal(state().state,'idle');
  emit('before_agent_start',{prompt:'MUST_NOT_BE_STORED'});emit('agent_start');
  const generation=state().generation;assert.match(generation,/:1$/);assert.equal(state().state,'working');
  emit('ui_prompt_start',{title:'PRIVATE_TITLE'});assert.equal(state().state,'waiting');
  emit('ui_prompt_end');assert.equal(state().state,'working');
  emit('agent_settled');assert.equal(state().state,'done');assert.equal(state().generation,generation);
  assert.ok(!readFileSync(path,'utf8').includes('PRIVATE_TITLE'));
  assert.ok(!readFileSync(path,'utf8').includes('MUST_NOT_BE_STORED'));
  assert.equal(statSync(path).mode&0o777,0o600);
}));
test('bridge: agent_end between retries never reports a completed run',()=>fixture(({emit,state})=>{
  emit('session_start');emit('agent_start');const generation=state().generation;
  emit('agent_end');emit('agent_start');assert.equal(state().state,'working');assert.equal(state().generation,generation);
  emit('agent_settled');assert.equal(state().state,'done');
}));
test('bridge: idle UI and nested dialogs restore what they interrupted',()=>fixture(({emit,state})=>{
  emit('session_start');emit('ui_prompt_start');emit('ui_prompt_start');
  emit('ui_prompt_end');assert.equal(state().state,'waiting');emit('ui_prompt_end');assert.equal(state().state,'idle');
  emit('agent_start');emit('agent_settled');const generation=state().generation;
  emit('ui_prompt_start');emit('ui_prompt_end');assert.equal(state().state,'done');assert.equal(state().generation,generation);
}));
test('bridge: shutdown is idempotent and removes only its own status',()=>fixture(({emit,path})=>{
  emit('session_start');assert.ok(existsSync(path));emit('session_shutdown');emit('session_shutdown');assert.ok(!existsSync(path));
}));
for(const mode of ['print','json','rpc']) test(`bridge: ${mode} child cannot replace interactive pane state`,()=>fixture(({emit,path})=>{
  emit('session_start');emit('agent_start');emit('agent_settled');assert.ok(!existsSync(path));
},mode));
test('bridge: removing Tern plugin makes the loaded extension inactive',()=>fixture(({root,emit,path})=>{
  emit('session_start');rmSync(join(root,'plugins/tern-tab-enhancer'),{recursive:true});emit('agent_start');assert.ok(!existsSync(path));
}));
test('bridge: no Tern environment registers no handlers',()=>{
  const previous=process.env.TERN_PANE;delete process.env.TERN_PANE;
  try {let registrations=0;bridge({on:()=>registrations++});assert.equal(registrations,0);}
  finally {if(previous!==undefined)process.env.TERN_PANE=previous;}
});
