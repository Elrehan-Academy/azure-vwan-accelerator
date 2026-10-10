#!/usr/bin/env python3
"""Validate concrete local configuration files without Azure calls."""
import argparse
import sys
from core import load_config, print_summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('configs', nargs='+')
    args = parser.parse_args()
    for path in args.configs:
        c = load_config(path)
        print_summary(c)
        print('PASS:', path)
    print('Local validation only; no Azure calls.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print('FAIL:', error, file=sys.stderr)
        sys.exit(1)
