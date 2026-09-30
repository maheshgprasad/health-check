#!/usr/bin/env python3
import sys

from healthcheck.cli import main

if __name__ == "__main__":
    sys.exit(main(["--only", "redis", *sys.argv[1:]]))
