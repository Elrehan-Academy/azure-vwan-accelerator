#!/usr/bin/env python3
"""Rebuild ARM templates from Bicep. Needed only when changing source."""
import argparse
import json
import shutil
import subprocess
import sys
from core import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bicep', help='Path to standalone Bicep CLI; otherwise use PATH or az bicep.')
    args = parser.parse_args()
    if args.bicep:
        cmd = [args.bicep]
    elif shutil.which('bicep'):
        cmd = ['bicep']
    elif shutil.which('az'):
        cmd = ['az', 'bicep']
    else:
        raise RuntimeError('Install Bicep CLI or Azure CLI with Bicep to rebuild. The ZIP already includes compiled templates.')
    subprocess.run([sys.executable, str(ROOT / 'scripts/multi-hub-core/check-workbooks.py')], check=True)
    for name, output in (('main', 'mainTemplate'), ('bootstrap', 'bootstrapTemplate')):
        subprocess.run([*cmd, 'build', *(['--file'] if cmd == ['az', 'bicep'] else []), str(ROOT / 'blueprints/multi-hub' / (name + '.bicep')),
                        '--outfile', str(ROOT / 'portal/multi-hub' / (output + '.json'))], check=True)
        target = ROOT / 'portal/multi-hub' / (output + '.json')
        if target.stat().st_size >= 4 * 1024 * 1024:
            raise RuntimeError(f'Template exceeds the 4 MiB size guard: {target}')
        json.loads(target.read_text())
    print('PASS: both templates compiled. Review the generated templates before committing.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print('FAIL:', error, file=sys.stderr)
        sys.exit(1)
