import assert from 'node:assert/strict';
import {readFile, stat} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {LuauState} from 'luau-web';

const root = new URL('../', import.meta.url);
const read = name => readFile(new URL(name, root), 'utf8');
const sources = Object.fromEntries(await Promise.all(
  ['model.luau', 'presentation.luau', 'host.luau', 'window.luau', 'runtime.luau', 'tests/behavior.luau']
    .map(async name => [name, await read(name)]),
));
const manifest = await read('plugin.toml');
const pkg = JSON.parse(await read('package.json'));
const lock = JSON.parse(await read('package-lock.json'));
assert.match(manifest, new RegExp(`id = "${pkg.name}"`));
assert.match(manifest, new RegExp(`version = "${pkg.version.replaceAll('.', '\\.')}"`));
assert.equal(lock.packages[''].version, pkg.version);
for (const name of ['host.luau', 'window.luau', 'runtime.luau', 'model.luau', 'presentation.luau']) {
  await stat(new URL(name, root));
}

const vm = await LuauState.createAsync();
try {
  for (const [name, source] of Object.entries(sources)) vm.loadstring(source, name, true);
  const run = vm.loadstring(`
local modules = {}
modules["./model"] = (function() ${sources['model.luau']} end)()
modules["./presentation"] = (function() ${sources['presentation.luau']} end)()
modules["./runtime"] = (function() ${sources['runtime.luau']} end)()
local function require(name) assert(modules[name], name); return modules[name] end
local function load_host_plugin(api)
  local tern = api
  ${sources['host.luau']}
end
local function load_window_plugin(api)
  local tern = api
  local function require(name)
    if api.on_require then api.on_require(name) end
    assert(modules[name], name); return modules[name]
  end
  ${sources['window.luau']}
end
${sources['tests/behavior.luau']}
`, 'runtime-behavior', true);
  const [passed] = await run();
  assert.equal(typeof passed, 'number');
  console.log(`PASS: ${passed} behavior cases; actual Luau modules compiled and executed.`);
} finally {
  vm.destroy();
}
assert.doesNotMatch(sources['window.luau'] + sources['runtime.luau'], /cx\.settings|color_tab|chrome\.tab_title|cx:run/);
assert.doesNotMatch(sources['host.luau'] + sources['window.luau'] + sources['runtime.luau'], /tern\.fetch|tern\.process/);
console.log(`PASS: native preferences, manual colors and titles remain outside the plugin's write surface.`);
const bridgeTests = spawnSync(process.execPath, ['--test', '--test-reporter=tap', fileURLToPath(new URL('tests/bridge.test.mjs', root))], {encoding:'utf8'});
assert.equal(bridgeTests.status, 0, bridgeTests.stdout + bridgeTests.stderr);
console.log(`PASS: ${bridgeTests.stdout.match(/# tests (\d+)/)?.[1] ?? 'all'} Pi bridge lifecycle and privacy cases.`);
console.log(`Project: ${fileURLToPath(root)}`);
