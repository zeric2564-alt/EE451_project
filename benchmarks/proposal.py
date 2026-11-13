#!/usr/bin/env python3
"""Sequential, resumable proposal experiments with immutable run provenance."""
import argparse
import csv
import datetime
import fcntl
import hashlib
import json
import math
import os
import platform
import random
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENES = ['room', 'uneven', 'bunny']
MODES = ['row-static', 'row-dynamic', 'tile-static', 'tile-dynamic']
STAGES = ['main', 'tiles', 'quality', 'cold', 'diagnostics']
KEY_FIELDS = ['scene', 'mode', 'threads', 'width', 'height', 'spp', 'depth', 'tile', 'chunk', 'seed', 'round']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture(command):
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return 'unavailable: ' + str(exc)


def read_optional(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def available_cpus():
    n = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else (os.cpu_count() or 1)
    quota = read_optional('/sys/fs/cgroup/cpu.max')
    if quota:
        amount, period = quota.split()
        if amount != 'max':
            n = min(n, max(1, math.ceil(int(amount) / int(period))))
    return n


def configurations(stage, threads, preset='proposal'):
    size, samples = (67, 2) if preset == 'smoke' else (512, 32)
    result = []
    for scene in SCENES:
        if stage == 'main':
            values = [(m, n, size, samples, 16) for m, n in [('serial', 1)] + [(m, n) for n in threads for m in MODES]]
        elif stage == 'tiles':
            values = [(m, max(threads), size, samples, tile) for m in ['tile-static', 'tile-dynamic'] for tile in [8, 16, 32, 64]]
        elif stage == 'quality':
            workloads = {'room': [(512, 64), (1024, 64)], 'uneven': [(512, 128)], 'bunny': [(1024, 32), (1024, 128)]}
            selected = workloads[scene]
            if preset == 'smoke':
                selected = [(67 if w == 512 else 97, 3 if s < 128 else 4) for w, s in selected]
            values = [(m, n, w, s, 16) for w, s in selected for m, n in [('serial', 1), ('tile-dynamic', max(threads))]]
        elif stage == 'cold':
            values = [(m, n, size, samples, 16) for m, n in [('serial', 1), ('tile-dynamic', max(threads))]]
        else:
            values = [(m, max(threads), size, samples, 16) for m in MODES]
        for mode, n, width, spp, tile in values:
            result.append(dict(scene=scene, mode=mode, threads=n, width=width, height=width, spp=spp, depth=10, tile=tile, chunk=1, seed=451))
    if stage == 'diagnostics':
        result += [dict(c, scene='bunny-mixed') for c in result if c['scene'] == 'bunny']
    return result


def key(row):
    return tuple(str(row[k]) for k in KEY_FIELDS)


def image_key(row):
    return tuple(str(row[k]) for k in ['scene', 'width', 'height', 'spp', 'depth', 'seed'])


def check_rows(rows, planned):
    allowed = {key(c) for c in planned}
    seen, hashes = set(), {}
    for row in rows:
        try:
            k, h = key(row), image_key(row)
            if k not in allowed or k in seen:
                raise ValueError('Unexpected or duplicate configuration/round')
            if int(row['actual_threads']) != int(row['threads']):
                raise ValueError('Requested workers were not honored')
            if not row['hash'] or (h in hashes and hashes[h] != row['hash']):
                raise ValueError('Image hash mismatch')
            if not math.isfinite(float(row['render_s'])) or float(row['render_s']) <= 0:
                raise ValueError('Invalid render time')
            seen.add(k)
            hashes[h] = row['hash']
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'Invalid or incomplete benchmark row: {exc}') from exc
    return seen, hashes


def provenance(args, env):
    binary_hash = digest(ROOT / 'raytrace')
    build_path = ROOT / 'build-info.json'
    if not build_path.exists():
        raise ValueError('Build metadata missing: rebuild with make -B before benchmarking.')
    build = json.loads(build_path.read_text())
    if build.get('binary_sha256') != binary_hash:
        raise ValueError('Build metadata does not match raytrace: rebuild with make -B.')
    return dict(schema_version=2, binary_sha256=binary_hash, build=build,
                sources={str(f.relative_to(ROOT)): digest(f) for f in sorted((ROOT/'src').glob('*'))},
                bunny_sha256=digest(ROOT/'assets/bunny.obj'), runner_sha256=digest(__file__),
                host=platform.node(), platform=platform.platform(), logical_cpus=os.cpu_count(), available_cpus=available_cpus(),
                cpu=capture(['sysctl', '-n', 'machdep.cpu.brand_string', 'hw.physicalcpu', 'hw.logicalcpu', 'hw.memsize']) if platform.system() == 'Darwin' else capture(['lscpu']),
                runtime=capture(['otool', '-L', str(ROOT/'raytrace')]) if platform.system() == 'Darwin' else capture(['ldd', str(ROOT/'raytrace')]),
                affinity=sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else 'OS-managed',
                cpu_quota=read_optional('/sys/fs/cgroup/cpu.max'),
                environment={k: v for k, v in env.items() if k.startswith(('OMP_', 'KMP_', 'GOMP_'))},
                threads=args.threads, repeats=args.repeats, preset=args.preset)


def ensure_provenance(out, identity):
    path = out / 'run.metadata.json'
    if path.exists():
        previous = json.loads(path.read_text())
        if previous['identity'] != identity:
            changed = sorted(k for k in set(previous['identity']) | set(identity) if previous['identity'].get(k) != identity.get(k))
            raise ValueError('Run environment changed (' + ', '.join(changed) + '); use a new --output directory.')
    else:
        if any((out/(s+'.csv')).exists() for s in STAGES):
            raise ValueError('Existing measurements have no matching run provenance; use a new --output directory.')
        path.write_text(json.dumps(dict(start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), identity=identity), indent=2)+'\n')


def run_stage(stage, args, env):
    out = args.output
    path = out / (stage + '.csv')
    rng = random.Random(451)
    planned = []
    for repeat in range(1 if stage == 'diagnostics' else args.repeats):
        block = [dict(c, round=repeat) for c in configurations(stage, args.threads, args.preset)]
        rng.shuffle(block)
        planned.extend(block)
    if path.exists():
        with path.open(newline='') as f:
            reader = csv.DictReader(f)
            columns, old = reader.fieldnames, list(reader)
        if not columns:
            raise ValueError(f'Empty CSV: inspect/remove {path} before resuming.')
    else:
        columns, old = None, []
    done, hashes = check_rows(old, planned)
    if stage == 'diagnostics':
        for row in old:
            for prefix in ['regions', 'threads']:
                artifact = out / f"{prefix}_{row['scene']}_{row['mode']}.csv"
                if not artifact.is_file():
                    raise ValueError(f'Missing retained diagnostic: {artifact}')
    if stage == 'cold':
        for row in old:
            if not (out/(row['scene']+'.png')).is_file():
                raise ValueError('Missing retained cold-run image; inspect this dataset before resuming.')
    meta_path = out / (stage + '.metadata.json')
    metadata = dict(stage=stage, preset=args.preset, expected_rows=len(planned), warmup=stage != 'cold',
                    timing_note='Warmed process_wall_s includes two renders; use cold.csv for single-frame process latency.',
                    run_metadata='run.metadata.json')
    with path.open('a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns) if columns else None
        for i, config in enumerate(planned):
            if key(config) in done:
                continue
            command = [str(ROOT/'raytrace')]
            for k, v in config.items():
                if k != 'round':
                    command += ['--'+k, str(v)]
            command += ['--warmup', '0' if stage == 'cold' else '1']
            if stage == 'cold':
                command += ['--output', str(out/(config['scene']+'.png'))]
            if stage == 'diagnostics':
                command += ['--regions', str(out/f"regions_{config['scene']}_{config['mode']}.csv"), '--diagnostics', str(out/f"threads_{config['scene']}_{config['mode']}.csv")]
            before = time.monotonic()
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=True)
            row = json.loads(result.stdout)
            row.update(round=config['round'], process_wall_s=time.monotonic()-before, utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            check_rows([row], [config])
            h = image_key(row)
            if h in hashes and hashes[h] != row['hash']:
                raise ValueError('Image hash changed across schedules')
            hashes[h] = row['hash']
            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(row))
                writer.writeheader()
            writer.writerow(row)
            f.flush()
            done.add(key(row))
            print(f"{stage} {i+1}/{len(planned)} {config['scene']} {config['mode']} {config['threads']}t: {row['render_s']:.4f}s", flush=True)
    metadata.update(rows=len(done), complete=len(done) == len(planned), completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    meta_path.write_text(json.dumps(metadata, indent=2)+'\n')
    print(f'{stage}: {len(done)}/{len(planned)} records retained', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', choices=STAGES+['all'], default='all')
    p.add_argument('--threads', nargs='+', type=int)
    p.add_argument('--repeats', type=int, default=5)
    p.add_argument('--output', type=Path, default=ROOT/'results/current/experiment')
    p.add_argument('--preset', choices=['proposal', 'smoke'], default='proposal', help='smoke validates the pipeline at reduced resolution/spp; not performance evidence')
    args = p.parse_args()
    args.threads = args.threads or [n for n in [1, 2, 4, 8] if n <= available_cpus()]
    if args.repeats < 5:
        p.error('Proposal requires at least five repetitions')
    if len(set(args.threads)) != len(args.threads) or any(n not in [1, 2, 4, 8] or n > available_cpus() for n in args.threads):
        p.error('Use unique supported worker counts from 1, 2, 4, 8')
    args.threads.sort()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OMP_DYNAMIC='FALSE', OMP_PROC_BIND='FALSE' if platform.system() == 'Darwin' else 'close', OMP_WAIT_POLICY='PASSIVE')
    if platform.system() == 'Darwin':
        env.pop('OMP_PLACES', None)
    else:
        env['OMP_PLACES'] = 'cores'
    try:
        with (args.output/'.run.lock').open('w') as lockfile:
            try:
                fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('Another benchmark is using this output directory.')
            ensure_provenance(args.output, provenance(args, env))
            for stage in STAGES if args.stage == 'all' else [args.stage]:
                run_stage(stage, args, env)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        p.exit(1, str(exc)+'\n')


if __name__ == '__main__':
    main()
