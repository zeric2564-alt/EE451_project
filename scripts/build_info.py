"""Record the compiler actually selected by Make, rather than guessing its name."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', required=True)
    parser.add_argument('--flags', required=True)
    args = parser.parse_args()
    Path('build-info.json').write_text(json.dumps({
        'compiler': args.compiler,
        'compiler_version': subprocess.check_output([args.compiler, '--version'], text=True),
        'flags': args.flags,
        'binary_sha256': hashlib.sha256(Path('raytrace').read_bytes()).hexdigest(),
    }, indent=2) + '\n')
