# Norman Config

## Session Limits
max_tasks_per_session: 15
warn_at_tasks: 12

## Project
name: Conary Python 3 port
repo: https://github.com/lhaig/conary (branch py3, upstream sassoftware/conary)
created: 2026-11-22

## Commands
# All commands run inside the Fedora dev container (task 1.1 creates it).
# Replace these placeholders with the real invocations when 1.1 is done.
build: TBD (task 1.1) -- e.g. scripts/devenv make
test: TBD (task 1.1) -- e.g. scripts/devenv python3 -m pytest <path>
lint: TBD (task 1.1) -- e.g. scripts/devenv python3 -m compileall -q conary conary_test commands scripts

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
