#!/bin/bash
# Environment for running the pipeline in WSL Ubuntu (no sudo needed).
# Setup used on this machine:
#   - JDK 17 (Temurin) unpacked to ~/tools/jdk17
#   - Python 3.12 venv at ~/venvs/oua with requirements.txt installed (via uv)
#   - libgomp1 extracted from the apt package into ~/tools/libgomp (LightGBM needs it)
# Spark writes to a Linux path because NTFS mounts (/mnt/c) reject chmod.
export JAVA_HOME=$HOME/tools/jdk17
export PATH="$JAVA_HOME/bin:$HOME/venvs/oua/bin:$PATH"
export LD_LIBRARY_PATH=$HOME/tools/libgomp/usr/lib/x86_64-linux-gnu
export PYTHONPATH=src
export OUA_DATA_DIR=$HOME/oua-data
export SPARK_LOCAL_DIRS=$HOME/tools/spark-tmp
mkdir -p "$OUA_DATA_DIR" "$SPARK_LOCAL_DIRS"
cd "$(dirname "$0")/.." || exit 1
