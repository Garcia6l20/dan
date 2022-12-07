#!/usr/bin/env python3

from pymake import cli, include

include('simple')
include('libraries')
include('qt')
include('modules')

if __name__ == '__main__':
    cli()
