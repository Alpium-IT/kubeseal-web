# syntax=docker/dockerfile:1
ARG NICEGUI_VERSION=99.99
FROM zauberzeug/nicegui:${NICEGUI_VERSION}


ARG NICEGUI_VERSION=99.99
ARG KUBESEAL_VERSION=99.99

ENV \
  KUBESEAL_VERSION=${KUBESEAL_VERSION} \
  NICEGUI_VERSION=${NICEGUI_VERSION} \
  CONFIG=/config/config.yaml \
  PUID=1001 \
  PGID=1001 \
  DEBIAN_FRONTEND=noninteractive

RUN <<EOT
    apt update
    apt upgrade -y
    apt install -y curl
    rm -rf /var/lib/apt/lists/*

    # Set permissions on font directories.
    if [ -d "/usr/share/fonts" ]; then
      chmod -R 777 /usr/share/fonts
    fi
    if [ -d "/var/cache/fontconfig" ]; then
      chmod -R 777 /var/cache/fontconfig
    fi
    if [ -d "/usr/local/share/fonts" ]; then
      chmod -R 777 /usr/local/share/fonts
    fi

    mkdir /config
    chgrp -R 0 /app
    chmod -R g+rwX /app /config

    # download 'kubeseal' from Bitnami GH release page
    curl -sSL -o kubeseal.tgz https://github.com/bitnami-labs/sealed-secrets/releases/download/v${KUBESEAL_VERSION}/kubeseal-${KUBESEAL_VERSION}-linux-amd64.tar.gz
    tar xvzf kubeseal.tgz kubeseal
    rm -f kubeseal.tgz
    mv kubeseal /usr/local/bin/
    chmod +rx /usr/local/bin/kubeseal
EOT

ADD --chmod=444 /app/main.py  /app
ADD --chmod=555 bin/openshift-entrypoint.sh /usr/local/bin/


ENTRYPOINT  [ "/usr/local/bin/openshift-entrypoint.sh" ]
# ENTRYPOINT  [ "/resources/docker-entrypoint.sh" ]
CMD ["python", "main.py"]
