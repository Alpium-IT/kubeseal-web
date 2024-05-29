# syntax=docker/dockerfile:1
FROM zauberzeug/nicegui:1.4.26

ENV CONFIG=/config/config.yaml

RUN <<EOT
    apt update 
    apt upgrade -y
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
EOT

ADD --chmod=444 /app/main.py  /app
ADD --chmod=555 bin/kubeseal bin/openshift-entrypoint.sh /usr/local/bin/


ENTRYPOINT  [ "/usr/local/bin/openshift-entrypoint.sh" ]
CMD ["python", "main.py"]
