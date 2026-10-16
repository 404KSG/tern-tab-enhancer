#!/usr/bin/env python3
"""Transactional local-copy install; native preferences are never edited."""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from package_plugin import PROJECT, stage_package

PLUGIN_ID = 'tern-tab-enhancer'
MARKER = '// Tern Tab Enhancer Pi bridge.'


def run(tern, *args):
    result = subprocess.run([tern,*map(str,args)],capture_output=True,text=True,timeout=45)
    if result.returncode:
        raise RuntimeError(f'Tern {args[0]} 失败：{result.stderr.strip() or result.stdout.strip()}')
    return result.stdout


@contextlib.contextmanager
def installation_lock(plugin_root):
    data = plugin_root.parent/'plugin-data'
    data.mkdir(parents=True,exist_ok=True)
    with (data/(PLUGIN_ID+'-installer.lock')).open('a') as handle:
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('另一个安装或卸载正在进行，请稍后重试') from None
        try:
            yield
        finally:
            fcntl.flock(handle,fcntl.LOCK_UN)


def atomic_copy(source, destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.tte-',suffix='.tmp',dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        shutil.copy2(source,temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def verify_owner(plugin_root, target, bridge, use_bridge):
    if target.is_symlink() or (plugin_root/(PLUGIN_ID+'.path')).exists():
        raise RuntimeError('当前是链接安装，请先明确 unlink；安装器不会覆盖源码链接')
    if target.exists():
        manifest = target/'plugin.toml'
        if not manifest.is_file() or not re.search(r'^id\s*=\s*"tern-tab-enhancer"\s*$',manifest.read_text(),re.M):
            raise RuntimeError(f'拒绝修改不属于本插件的目录：{target}')
    if use_bridge and (bridge.exists() or bridge.is_symlink()):
        if bridge.is_symlink() or not bridge.is_file() or not bridge.read_text().startswith(MARKER):
            raise RuntimeError(f'拒绝覆盖或删除其他扩展：{bridge}')


class TransactionWorkspace:
    """Never delete the original backup when recovery itself fails."""
    def __init__(self):
        self.path = Path(tempfile.mkdtemp(prefix='tte-transaction-'))
        self.preserve = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if not self.preserve:
            shutil.rmtree(self.path,ignore_errors=True)


def transact(args):
    tern = args.tern or shutil.which('tern') or '/Applications/Tern.app/Contents/MacOS/tern'
    plugin_root = Path(run(tern,'plugin','dir').strip()).expanduser()
    if not plugin_root.is_absolute():
        raise RuntimeError('Tern 返回了非绝对插件目录，停止操作')
    target = plugin_root/PLUGIN_ID
    agent = (args.pi_agent_dir or Path(os.environ.get('PI_CODING_AGENT_DIR',str(Path.home()/'.pi/agent')))).expanduser()
    bridge = agent/'extensions/tern-tab-enhancer.ts'
    use_bridge = not args.without_pi_bridge
    with installation_lock(plugin_root), TransactionWorkspace() as workspace:
        work = workspace.path
        verify_owner(plugin_root,target,bridge,use_bridge)
        had_plugin, had_bridge = target.exists(), bridge.exists() if use_bridge else False
        if had_plugin and not args.force and not args.uninstall:
            raise RuntimeError('插件已存在；更新请传 --force')
        if had_plugin:
            shutil.copytree(target,work/'old-plugin')
        if had_bridge:
            shutil.copy2(bridge,work/'old-bridge.ts')
        prepared = None
        touched_plugin = touched_bridge = False
        try:
            if not args.uninstall:
                stage_package(work/'new-plugin')
                # Probe writability and stage the bridge before touching Tern.
                if use_bridge:
                    bridge.parent.mkdir(parents=True,exist_ok=True)
                    descriptor,name = tempfile.mkstemp(prefix='.tte-',suffix='.tmp',dir=bridge.parent)
                    os.close(descriptor);prepared=Path(name)
                    shutil.copy2(PROJECT/'pi/bridge.ts',prepared)
                touched_plugin = True
                install_args = ['plugin','install',work/'new-plugin','--json']
                if had_plugin or args.force:install_args.append('--force')
                run(tern,*install_args)
                catalog = json.loads(run(tern,'plugin','list','--json'))
                own = [p for p in catalog.get('plugins',[]) if p.get('id')==PLUGIN_ID]
                if len(own)!=1 or own[0].get('status')!='ready':
                    raise RuntimeError('插件安装后未进入 ready 状态')
                if prepared:
                    touched_bridge = True
                    prepared.replace(bridge);prepared=None
                    if bridge.read_bytes()!=(PROJECT/'pi/bridge.ts').read_bytes():
                        raise RuntimeError('Pi 状态桥复制校验失败')
            else:
                # A failed Tern removal must never remove the still-needed bridge.
                if had_plugin:
                    touched_plugin = True
                    run(tern,'plugin','remove',PLUGIN_ID,'--json')
                if had_bridge:
                    touched_bridge = True
                    bridge.unlink()
            catalog = json.loads(run(tern,'plugin','list','--json'))
        except Exception as original:
            rollback_errors = []
            if touched_bridge:
                try:
                    if had_bridge:atomic_copy(work/'old-bridge.ts',bridge)
                    else:bridge.unlink(missing_ok=True)
                except Exception as error:rollback_errors.append(f'Pi 桥：{error}')
            if touched_plugin:
                try:
                    if target.is_symlink():raise RuntimeError('目标在操作期间变成了符号链接')
                    if target.exists():shutil.rmtree(target)
                    if had_plugin:shutil.copytree(work/'old-plugin',target)
                    try:run(tern,'plugin','reload','--json')
                    except Exception as error:rollback_errors.append(f'文件已恢复，但 Tern 重载未确认：{error}')
                except Exception as error:rollback_errors.append(f'Tern 插件文件：{error}')
            if rollback_errors:
                workspace.preserve = True
                raise RuntimeError(f'{original}\n回滚未完全确认：{"；".join(rollback_errors)}\n旧文件备份原地保留：{work}') from original
            raise RuntimeError(f'{original}\n已恢复操作前的插件与 Pi 桥文件。') from original
        finally:
            if prepared:prepared.unlink(missing_ok=True)
        print(json.dumps(catalog,ensure_ascii=False,indent=2))
        if args.uninstall:
            print('已卸载插件' + ('及 Pi 状态桥。' if use_bridge else '；Pi 状态桥保持原样。'))
        else:
            print('插件安装完成，原生设置未修改。')
            if use_bridge:print('已有 Pi 会话请空闲后执行 /reload；新会话自动加载状态桥。')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--tern')
    parser.add_argument('--without-pi-bridge',action='store_true')
    parser.add_argument('--pi-agent-dir',type=Path)
    parser.add_argument('--uninstall',action='store_true')
    try:transact(parser.parse_args())
    except Exception as error:
        print(str(error),file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
