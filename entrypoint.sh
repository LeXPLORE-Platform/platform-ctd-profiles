#!/bin/bash

. /opt/conda/etc/profile.d/conda.sh
conda activate pipeline
git config --global --add safe.directory /repository
cd /repository
python -u scripts/pipeline.py "$@"