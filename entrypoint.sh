#!/bin/bash
if [ "$#" -eq 0 ]; then
  python ./getorphanedvms.py --help
else
  python ./getorphanedvms.py "$@"
fi
