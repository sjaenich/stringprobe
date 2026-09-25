# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.14.3-slim-bookworm@sha256:f21c0d5a44c56805654c15abccc1b2fd576c8d93aca0a3f74b4aba2dc92510e2
FROM ${PYTHON_IMAGE}
ARG TARGETARCH
RUN test "${TARGETARCH}" = amd64

# Buildroot host tools and SuperC's Java/native dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    autoconf automake bc bison build-essential ca-certificates cmake cpio \
    file flex gawk gettext git gzip bzip2 diffutils findutils sed tar debianutils libelf-dev libncurses-dev libssl-dev libtool \
    libjson-java libz3-java libz3-jni openjdk-17-jdk-headless patch perl \
    pkg-config python3 rsync sat4j texinfo unzip wget xz-utils \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONHASHSEED=0 \
    LC_ALL=C.UTF-8 LANG=C.UTF-8 TZ=UTC \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    JAVA_DEV_ROOT=/opt/artifact/string-probe/superc \
    PYTHONPATH=/opt/artifact/string-probe:/opt/artifact/string-probe/feature-tests \
    ARTIFACT_ROOT=/opt/artifact
ENV CLASSPATH=${JAVA_DEV_ROOT}/classes:${JAVA_DEV_ROOT}/bin/junit.jar:${JAVA_DEV_ROOT}/bin/antlr.jar:${JAVA_DEV_ROOT}/bin/javabdd.jar:${JAVA_DEV_ROOT}/bin/json-simple-1.1.1.jar:/usr/share/java/org.sat4j.core.jar:/usr/share/java/com.microsoft.z3.jar:/usr/share/java/json-lib.jar

WORKDIR /opt/artifact
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock
COPY string-probe/ ./string-probe/
# This branch has no installable root package. Expose its actual package name.
RUN ln -sfn compiler-provenance string-probe/compiler_provenance \
    && mkdir -p string-probe/superc/classes
RUN make -C string-probe/superc configure
RUN make -C string-probe/superc
COPY artifact/ ./artifact/
COPY configs/ ./configs/
COPY downloads/ ./downloads/
RUN ln -s /opt/artifact/artifact/cli.py /usr/local/bin/artifact \
    && chmod +x artifact/cli.py \
    && useradd --create-home --uid 1000 artifact \
    && mkdir -p /workspaces/RevEng /results \
    && for log in logs logs-O0 logs-O2 logs-Os; do \
         if [ -d "string-probe/feature-tests/$log" ]; then mv "string-probe/feature-tests/$log" "string-probe/feature-tests/recorded-$log"; fi; \
         ln -s "/results/$log" "string-probe/feature-tests/$log"; \
       done \
    && chown -R artifact:artifact /opt/artifact /workspaces/RevEng /results
USER artifact
WORKDIR /results
# Exercise the two Python repositories and the real SuperC implementation.
RUN artifact smoke
ENTRYPOINT ["artifact"]
CMD ["help"]
