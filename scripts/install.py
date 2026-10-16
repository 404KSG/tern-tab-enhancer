#!/usr/bin/env python3
"""Install the runtime plus the small Pi status bridge; never edit preferences."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import json

parser = argparse.ArgumentParser()
parser.add_argument('--force', action='store_true')
parser.add_argument('--tern')
parser.add_argument('--without-pi-bridge', action='store_true')
parser.add_argument('--pi-agent-dir', type=Path)
parser.add_argument('--uninstall', action='store_true')
args = parser.parse_args()
project = Path(__file__).resolve().parents[1]
tern = args.tern or shutil.which('tern') or '/Applications/Tern.app/Contents/MacOS/tern'
agent_dir = args.pi_agent_dir or Path(os.environ.get('PI_CODING_AGENT_DIR',str(Path.home()/'.pi/agent')))
bridge_target = agent_dir/'extensions/tern-tab-enhancer.ts'
marker = '// Tern Tab Enhancer Pi bridge.'


def own_bridge():
    return bridge_target.is_file() and bridge_target.read_text().startswith(marker)


if args.uninstall:
    if own_bridge():
        bridge_target.unlink()
        print(f'已移除 Pi 状态桥：{bridge_target}')
    result = subprocess.run([tern,'plugin','list','--json'],check=True,capture_output=True,text=True)
    if any(p.get('id')=='tern-tab-enhancer' for p in json.loads(result.stdout).get('plugins',[])):
        subprocess.run([tern,'plugin','remove','tern-tab-enhancer','--json'],check=True)
else:
    if not args.without_pi_bridge and (bridge_target.exists() or bridge_target.is_symlink()):
        if bridge_target.is_symlink() or not own_bridge():
            raise SystemExit(f'拒绝覆盖其他扩展：{bridge_target}')
    files = ['plugin.toml','host.luau','window.luau','runtime.luau','model.luau','presentation.luau',
             'LICENSE','README.md','THIRD_PARTY_NOTICES.md','pi/bridge.ts','docs/README.md',
             'docs/design/tab-enhancement.md','docs/reports/verification.md','docs/reports/tab-preview.png']
    with tempfile.TemporaryDirectory(prefix='tern-tab-enhancer-package-') as folder:
        stage = Path(folder)
        for name in files:
            (stage/name).parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(project/name,stage/name)
        command = [tern,'plugin','install',str(stage),'--json']
        if args.force:
            command.append('--force')
        subprocess.run(command,check=True)
    if not args.without_pi_bridge:
        bridge_target.parent.mkdir(parents=True,exist_ok=True)
        temporary = bridge_target.with_suffix('.ts.tmp')
        shutil.copy2(project/'pi/bridge.ts',temporary)
        temporary.replace(bridge_target)
        print(f'已安装 Pi 状态桥：{bridge_target}')
        print('已打开的 Pi 会话请在空闲后执行 /reload，或重新启动 Pi。')
subprocess.run([tern,'plugin','list','--json'],check=True)
