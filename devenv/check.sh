#!/bin/bash
# Verifies the Conary dev container. Run as: devenv/run devenv/check.sh
set -eu

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }

command -v python3 >/dev/null 2>&1 || fail "python3 not found"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
    || fail "python3 is older than 3.12"
ok "python3 $(python3 -c 'import platform; print(platform.python_version())') (>= 3.12)"

command -v python3.11 >/dev/null 2>&1 || fail "python3.11 not found"
python3.11 -W ignore -c 'import lib2to3, lib2to3.main' || fail "python3.11 cannot import lib2to3"
ok "python3.11 $(python3.11 -c 'import platform; print(platform.python_version())') with lib2to3"

python3 -c 'import Cython' || fail "Cython not importable for python3"
cyver=$(python3 -m cython --version 2>&1) || fail "cython not runnable for python3"
ok "Cython $cyver"
pfver=$(python3 -m pyflakes --version 2>&1) || fail "pyflakes not runnable for python3"
ok "pyflakes $pfver"

python3 -c 'import Cryptodome.Cipher.CAST, Cryptodome.Cipher.Blowfish, Cryptodome.Cipher.DES3, Cryptodome.Cipher.AES, Cryptodome.Hash.RIPEMD160' \
    || fail "pycryptodomex (Cryptodome) not importable for python3"
ok "pycryptodomex $(python3 -c 'import Cryptodome; print(Cryptodome.__version__)')"

for mod in rpm psycopg2 webob; do
    python3 -c "import $mod" || fail "$mod not importable for python3"
    ok "$mod importable for python3"
done

python3 -m pytest --version >/dev/null 2>&1 || fail "pytest not runnable"
python3 -c "import pytest_timeout" || fail "pytest-timeout not importable for python3"
ok "pytest-timeout importable for python3"
T=$(mktemp -d /tmp/devenv-check.XXXXXX)
trap 'rm -rf "$T"' EXIT
printf 'def test_ok():\n    assert 1 + 1 == 2\n' > "$T/test_smoke.py"
python3 -m pytest -q -p no:cacheprovider "$T/test_smoke.py" >/dev/null || fail "pytest could not run a trivial test"
ok "pytest $(python3 -m pytest --version 2>&1 | head -1)"

command -v gcc >/dev/null 2>&1 || fail "gcc not found"
command -v python3-config >/dev/null 2>&1 || fail "python3-config not found"
cat > "$T/t.c" <<'CEOF'
#include <Python.h>
#include <openssl/evp.h>
#include <zlib.h>
#include <sqlite3.h>
#include <libelf.h>
#include <stdio.h>
int main(void) {
    EVP_MD_CTX *c = EVP_MD_CTX_new();
    printf("zlib %s sqlite %s elf %u python-init %d\n", zlibVersion(),
           sqlite3_libversion(), elf_version(EV_CURRENT), Py_IsInitialized());
    EVP_MD_CTX_free(c);
    return 0;
}
CEOF
# shellcheck disable=SC2046
gcc $(python3-config --includes) "$T/t.c" -o "$T/t" \
    $(python3-config --ldflags --embed) -lcrypto -lz -lsqlite3 -lelf \
    || fail "gcc could not compile/link against Python.h, openssl, zlib, sqlite3, libelf"
"$T/t" >/dev/null || fail "compiled test program did not run"
ok "gcc builds and links Python.h, openssl, zlib, sqlite3, libelf"

command -v make >/dev/null 2>&1 || fail "make not found"
ok "make $(make --version | head -1)"

[ "$PWD" = /src ] || fail "working directory is $PWD, expected /src"
[ -d conary/lib/ext ] || fail "conary/lib/ext not found: repo is not bind-mounted at /src"
ok "working directory /src is the repo (conary/lib/ext exists)"

echo "ALL CHECKS PASSED"
