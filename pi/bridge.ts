// Tern Tab Enhancer Pi bridge. Local status metadata only; no prompt or chat text.
import {existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';

export default function ternTabBridge(pi) {
  const pane = process.env.TERN_PANE;
  if (!pane || !/^\d+$/.test(pane) || !process.env.TERN_PANE_SOCKET) return;
  const config = process.env.TERN_CONFIG_DIR || (process.platform === 'darwin'
    ? join(homedir(), 'Library', 'Application Support', 'Tern') : undefined);
  if (!config) return;
  const manifest = join(config, 'plugins', 'tern-tab-enhancer', 'plugin.toml');
  if (!existsSync(manifest)) return;
  const directory = join(config, 'plugin-data', 'tern-tab-enhancer', 'bridge');
  const path = join(directory, `${pane}.json`);
  const temporary = join(directory, `${pane}.${process.pid}.tmp`);
  const instance = randomUUID();
  let active = false, timer, turn = 0, sequence = 0, running = false;
  let resting = 'idle', prompts = 0;

  function removeOwnFile() {
    try {
      if (JSON.parse(readFileSync(path, 'utf8')).instance === instance) unlinkSync(path);
    } catch {}
    try { unlinkSync(temporary); } catch {}
  }
  function shutdown() {
    if (timer) clearInterval(timer);
    timer = undefined;
    active = false;
    removeOwnFile();
  }
  function publish(takeover = false) {
    if (!active) return;
    if (!existsSync(manifest)) { shutdown(); return; }
    try {
      if (!takeover && existsSync(path)) {
        const owner = JSON.parse(readFileSync(path, 'utf8'));
        if (owner.instance !== instance) return;
      }
      mkdirSync(directory, {recursive: true, mode: 0o700});
      const report = {schema: 1, pane, pid: process.pid, instance,
        generation: `${instance}:${turn}`, sequence: ++sequence,
        state: prompts > 0 ? 'waiting' : resting};
      writeFileSync(temporary, JSON.stringify(report), {mode: 0o600});
      renameSync(temporary, path);
    } catch {
      // A display integration must never fail an agent tool or model turn.
    }
  }
  function begin() {
    if (!active) return;
    if (!running) turn += 1;
    running = true;
    resting = 'working';
    publish();
  }
  pi.on('session_start', (_event, ctx) => {
    // Child pi -p / RPC / JSON processes can inherit the same Tern pane.
    // They must never overwrite the interactive parent's indicator.
    if (ctx.mode !== 'tui') return;
    active = true;
    running = false;
    resting = 'idle';
    prompts = 0;
    publish(true);
    if (timer) clearInterval(timer);
    timer = setInterval(() => publish(), 5000);
    timer.unref?.();
  });
  pi.on('before_agent_start', begin);
  pi.on('agent_start', begin);
  // agent_end also fires between retries and continuations; settled is final.
  pi.on('agent_settled', () => {
    if (!active) return;
    running = false;
    resting = 'done';
    publish();
  });
  pi.on('ui_prompt_start', () => { if (active) { prompts += 1; publish(); } });
  pi.on('ui_prompt_end', () => { if (active) { prompts = Math.max(0, prompts - 1); publish(); } });
  pi.on('session_shutdown', shutdown);
}
