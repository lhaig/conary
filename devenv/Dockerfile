# Conary dev container. Fedora 45 is the current stable release (46 is rawhide).
FROM fedora:45
RUN dnf install -y --setopt=install_weak_deps=False \
        python3 python3-devel python3.11 python3-cython python3-pytest python3-pytest-timeout \
        python3-pyflakes python3-pycryptodomex python3-rpm python3-psycopg2 python3-webob gcc make git openssl-devel zlib-devel sqlite-devel \
        elfutils-libelf-devel which findutils diffutils file \
        cpio rpm-build patch unzip xz-lzma-compat python-unversioned-command \
    && dnf clean all \
    && git config --system --add safe.directory '*'
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
