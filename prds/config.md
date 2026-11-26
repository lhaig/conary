# Norman Config

## Session Limits
max_tasks_per_session: 15
warn_at_tasks: 12

## Project
name: Conary Python 3 port
repo: https://github.com/lhaig/conary (branch py3, upstream sassoftware/conary)
created: 2026-11-22

## Commands
# Everything runs in the Fedora 45 container via devenv/run (see devenv/README.md).
toolchain_check: devenv/run devenv/check.sh
2to3: devenv/run python3.11 -W ignore -m lib2to3 -w -n -j4 conary conary_test commands scripts
build: devenv/run make -C conary/lib/ext   (needs Make.rules fixes from task 1.3)
test: devenv/run python3 -m pytest -q py3tests </dev/null   (port regression suite)
conary_test: devenv/run sh -c 'make -C conary/lib/ext && make -C conary_test && python3 -m pytest conary_test' </dev/null   (add --collect-only -q for the collection gate, -m <context> to select)
baseline: devenv/conary_test_baseline.sh [outdir]; python3 devenv/triage.py [outdir]   (outdir relative to repo root, default tmp/baseline; ~81 min until 3.2)
compile_gate: devenv/compile_check.sh   (run on the host: it needs shasum, which the container lacks)
lint: devenv/run python3 -m compileall -q conary conary_test commands scripts ; devenv/run python3 -m pyflakes conary

## Subagent Defaults
default_subagent: general-purpose

## Model Strategy
advisor_mode: always
advisor_model: opus
default_model: sonnet
quick_model: haiku
progress_compress_after: 10
verify_rigor: single
security_max_reqs_per_prd: 8

## Cleanup
sweep_mode: offer
