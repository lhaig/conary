# Conary dev container

Conary is Linux-only. All building and testing runs in a Fedora 45 container
with this checkout bind-mounted at `/src` (also the working directory).

    devenv/run <command> [args...]    # e.g. devenv/run make -C conary/lib/ext
    devenv/run                        # interactive bash
    devenv/run devenv/check.sh        # verify the toolchain

- The image `conary-devenv:<hash>` is built on first use and rebuilt whenever
  `devenv/Dockerfile` changes (the tag is a hash of the Dockerfile). The build
  context is `devenv/` only.
- A TTY is allocated only when stdin is a terminal, so `devenv/run` works in
  pipes and scripts.
- The image provides Fedora's python3 (3.15, meets the >= 3.12 floor),
  python3.11 (only for lib2to3), gcc, make, git, Cython 3, pytest, pyflakes and
  openssl/zlib/sqlite/libelf headers.
- Ownership: Docker Desktop on macOS maps container-written files to your user.
  On native Linux the script passes `--user $(id -u):$(id -g)` and `HOME=/tmp`.
- Add packages to the Dockerfile, not ad hoc; keep this directory outside
  `scripts/` so 2to3 does not touch it.
