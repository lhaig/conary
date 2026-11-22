# Conary dev container. Fedora 45 is the current stable release (46 is rawhide).
FROM fedora:45
RUN dnf install -y --setopt=install_weak_deps=False \
        python3 python3-devel python3.11 python3-cython python3-pytest \
        python3-pyflakes gcc make git openssl-devel zlib-devel sqlite-devel \
        elfutils-libelf-devel which findutils diffutils file \
    && dnf clean all \
    && git config --system --add safe.directory '*'
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
