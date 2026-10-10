"""Install the pinned CUDA engine on GPU-Server without sudo or system-wide changes.

Run with Python 3.12: setup_engine.py --manifest models.json [--start].
Only this application's source, toolchain, models and user service are managed.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ENGINE_REPO = 'https://github.com/ServeurpersoCom/acestep.cpp.git'
ENGINE_REV = 'b7ba6d9ce2f19ca7627fb8f340032c3ebe8ae253'
CUDA_BASE = 'https://developer.download.nvidia.com/compute/cuda/redist/'
CUDA_PACKAGES = {
    'cuda_nvcc/linux-x86_64/cuda_nvcc-linux-x86_64-12.9.86-archive.tar.xz':
        '7a1a5b652e5ef85c82b721d10672fc9a2dbaab44e9bd3c65a69517bf53998c35',
    'cuda_cudart/linux-x86_64/cuda_cudart-linux-x86_64-12.9.79-archive.tar.xz':
        '1f6ad42d4f530b24bfa35894ccf6b7209d2354f59101fd62ec4a6192a184ce99',
    'libcublas/linux-x86_64/libcublas-linux-x86_64-12.9.1.4-archive.tar.xz':
        '546addc4a9d82b8f23aa9ba9274b6bc0429a63008a31c759884ac24880796057',
    'cuda_cccl/linux-x86_64/cuda_cccl-linux-x86_64-12.9.27-archive.tar.xz':
        '8b1a5095669e94f2f9afd7715533314d418179e9452be61e2fde4c82a3e542aa',
}


def run(*args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, target, expected, size=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if digest(target) == expected and (size is None or target.stat().st_size == size):
            print('Verified existing', target.name, flush=True)
            return target
        raise RuntimeError(f'Existing file has unexpected contents; preserved: {target}')
    partial = target.with_name(target.name + '.part')
    run('curl', '-L', '--fail', '--silent', '--show-error', '--retry', '3', '--continue-at', '-',
        '--output', partial, url)
    if digest(partial) != expected or (size is not None and partial.stat().st_size != size):
        raise RuntimeError(f'Download checksum/size mismatch: {partial}')
    partial.replace(target)
    print('Verified download', target.name, flush=True)
    return target


def toolkit(base):
    prefix = base / 'cuda-12.9.1'
    marker = prefix / '.complete.json'
    if marker.exists() and json.loads(marker.read_text()) == CUDA_PACKAGES:
        return prefix
    cache = base / 'downloads'
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(download, CUDA_BASE + rel, cache / Path(rel).name, sha)
                   for rel, sha in CUDA_PACKAGES.items()]
        archives = [f.result() for f in futures]
    prefix.mkdir(parents=True, exist_ok=True)
    unpack = base / 'unpacked'
    for archive in archives:
        package = unpack / archive.name.removesuffix('.tar.xz')
        if not package.exists():
            with tarfile.open(archive) as tar:
                tar.extractall(unpack, filter='data')
        # NVIDIA redistributables share bin/include/lib/nvvm directories.
        # Keep each original license in its package, outside the merged prefix.
        for entry in package.iterdir():
            if entry.is_dir():
                shutil.copytree(entry, prefix / entry.name, dirs_exist_ok=True, symlinks=True)
    if not (prefix / 'lib64').exists():
        (prefix / 'lib64').symlink_to('lib', target_is_directory=True)
    marker.write_text(json.dumps(CUDA_PACKAGES, indent=2) + '\n')
    return prefix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--lm', choices=['0.6B', '1.7B', '4B'], default='4B')
    parser.add_argument('--port', type=int, default=18085)
    parser.add_argument('--start', action='store_true')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if sys.platform != 'linux' or sys.version_info < (3, 12):
        parser.error('Use Python 3.12+ on the Linux GPU host.')
    if not 1024 <= args.port <= 65535 or not 1 <= args.jobs <= 16:
        parser.error('Port must be 1024..65535 and jobs 1..16.')
    for tool in ('git', 'curl', 'g++', 'nvidia-smi', 'systemctl'):
        if not shutil.which(tool):
            raise RuntimeError(f'Missing tool: {tool}')
    run('nvidia-smi', '--query-gpu=name,memory.free,driver_version', '--format=csv')
    base = Path.home() / '.local/share/music-generator-engine'
    source = Path.home() / 'apps/music-generator-engine'
    base.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run('git', 'clone', ENGINE_REPO, source)
    elif not (source / '.git').exists():
        raise RuntimeError(f'Existing folder is not the engine checkout: {source}')
    origin = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=source, text=True).strip()
    if origin.removesuffix('.git') != ENGINE_REPO.removesuffix('.git'):
        raise RuntimeError(f'Unexpected engine origin: {origin}')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=source, text=True).strip():
        raise RuntimeError('Engine checkout has local source changes; preserved.')
    run('git', 'checkout', '--detach', ENGINE_REV, cwd=source)
    run('git', 'submodule', 'update', '--init', '--recursive', cwd=source)
    cuda = toolkit(base)
    uv = Path.home() / '.local/bin/uv'
    if not uv.is_file():
        raise RuntimeError('Install uv in ~/.local/bin first.')
    cmake = [uv, 'tool', 'run', '--from', 'cmake==3.31.6', 'cmake']
    env = {**os.environ, 'PATH': str(cuda / 'bin') + ':' + os.environ['PATH'],
           'LD_LIBRARY_PATH': str(cuda / 'lib') + ':' + os.environ.get('LD_LIBRARY_PATH', '')}
    run(*cmake, '-S', source, '-B', source / 'build', '-DGGML_CUDA=ON',
        f'-DCMAKE_CUDA_COMPILER={cuda / "bin/nvcc"}', f'-DCUDAToolkit_ROOT={cuda}',
        '-DCMAKE_CUDA_ARCHITECTURES=120', '-DCMAKE_BUILD_TYPE=Release', env=env)
    run(*cmake, '--build', source / 'build', '--target', 'ace-server', '-j', args.jobs, env=env)
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    files = [f for f in manifest['files'] if not f['name'].startswith('acestep-5Hz-lm-')
             or f['name'] == f'acestep-5Hz-lm-{args.lm}-Q8_0.gguf']
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(download,
                   f'https://huggingface.co/{manifest["repo"]}/resolve/{manifest["revision"]}/{f["name"]}',
                   source / 'models' / f['name'], f['sha256'], f['size']) for f in files]
        for future in futures:
            future.result()
    unit = Path.home() / '.config/systemd/user/music-generator-engine.service'
    content = f'''[Unit]
Description=Music Generator ACE-Step CUDA engine

[Service]
Type=simple
WorkingDirectory={source}
Environment="LD_LIBRARY_PATH={cuda / 'lib'}"
ExecStart={source / 'build/ace-server'} --models {source / 'models'} --host 127.0.0.1 --port {args.port} --max-batch 1 --no-fa --clamp-fp16
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
'''
    unit.parent.mkdir(parents=True, exist_ok=True)
    previous = unit.read_text() if unit.exists() else None
    legacy = content.replace(' --no-fa --clamp-fp16', '')
    if previous is not None and previous not in (content, legacy):
        raise RuntimeError(f'Existing different user service preserved: {unit}')
    unit.write_text(content)
    (base / 'installation.json').write_text(json.dumps({
        'engine_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(),
        'models': manifest, 'lm': args.lm, 'port': args.port, 'cuda': '12.9.1'
    }, indent=2) + '\n')
    run('systemctl', '--user', 'daemon-reload')
    if args.start:
        # Refuse to take over an unrelated listener. Never stop other services.
        import socket
        with socket.socket() as probe:
            occupied = probe.connect_ex(('127.0.0.1', args.port)) == 0
        active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit.stem]).returncode == 0
        if occupied and not active:
            raise RuntimeError(f'Port {args.port} is occupied; existing listener preserved.')
        run('systemctl', '--user', 'restart' if active and previous != content else 'start', unit.stem)
    print(f'Ready. Start: systemctl --user start {unit.stem}', flush=True)


if __name__ == '__main__':
    main()
