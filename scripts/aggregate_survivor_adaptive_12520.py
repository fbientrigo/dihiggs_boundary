#!/usr/bin/env python3
"""Aggregate a fresh survivor-led 125.20 GeV campaign."""

import argparse
from dhb.survivor_adaptive_aggregate import aggregate_run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(); aggregate_run(args.run_dir)
