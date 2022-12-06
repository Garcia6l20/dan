#!/usr/bin/env python3

from pymake import cli, include

include('simple')
include('libraries')
include('qt')

if __name__ == '__main__':
    cli()
