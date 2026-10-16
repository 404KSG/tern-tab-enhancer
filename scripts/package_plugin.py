#!/usr/bin/env python3
"""One allow-list for installs, native verification and release archives."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile

PROJECT = Path(__file__).resolve().parents[1]


def package_files(project=PROJECT, runtime_only=False):
    manifest = json.loads((project/'package-files.json').read_text())
    names = manifest['runtime'] if runtime_only else sum(manifest.values(), [])
    if len(names) != len(set(names)):
        raise ValueError('打包清单包含重复文件')
    for name in names:
        relative = Path(name)
        forbidden = {'.git','node_modules','artifacts','dist','__pycache__','.venv'}
        if (relative.is_absolute() or '..' in relative.parts or forbidden.intersection(relative.parts)
                or any(part.startswith('.env') and part!='.env.example' for part in relative.parts)
                or relative.suffix=='.log'):
            raise ValueError(f'不安全或私有的打包路径：{name}')
        source = project/relative
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(project.resolve()):
            raise ValueError(f'打包文件不存在或为符号链接：{name}')
    return names


def stage_package(destination, project=PROJECT, runtime_only=False):
    hashes = {}
    for name in package_files(project, runtime_only):
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project/name, target)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    return hashes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tte-package-') as folder:
        stage = Path(folder)/'tern-tab-enhancer'
        hashes = stage_package(stage)
        (stage/'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2)+'\n')
        with tarfile.open(args.out, 'w:gz') as archive:
            archive.add(stage, arcname='tern-tab-enhancer', recursive=True)
    print(args.out.resolve())


if __name__ == '__main__':
    main()
