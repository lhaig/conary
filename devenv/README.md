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
- Non-root by default: `devenv/run` always passes `--user $(id -u):$(id -g)` and
  `HOME=/tmp`, on macOS as well as Linux, so files written to the bind mount belong to
  you and permission tests (for example in `py3tests/test_util_rmtree.py`) run instead of
  skipping as root. Set `DEVENV_ROOT=1` to run as root, for example to record which tests
  need root.
- Platform: `DEVENV_PLATFORM=linux/amd64 devenv/run <command>` runs the x86_64 image
  (emulated on Apple silicon). It passes `--platform` to `docker build` and `docker run`
  and uses the tag `conary-devenv:<hash>-amd64`; without it the tag stays
  `conary-devenv:<hash>` (native). `devenv/conary_test_baseline.sh` passes the variable
  through and records platform, `uname -m`, uid and git HEAD in `<outdir>/env.txt`.
  The repo is shared by both images: run `make -C conary/lib clean`, `make -C conary/lib/ext clean` and `make -C conary_test clean` before building for
  the other platform, because the compiled extensions are architecture specific.
- The image also has cpio, rpm-build, patch, unzip, lzma (xz-lzma-compat) and `python`
  (python-unversioned-command), which conary_test uses.
- Add packages to the Dockerfile, not ad hoc; keep this directory outside
  `scripts/` so 2to3 does not touch it.
