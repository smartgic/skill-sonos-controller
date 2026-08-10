ARG TAG=alpha
FROM smartgic/ovos-skill-base:${TAG}

ARG BUILD_DATE=unknown
ARG VERSION=unknown

LABEL org.opencontainers.image.title="Open Voice OS OCI SONOS controller skill image"
LABEL org.opencontainers.image.description="Control Sonos speakers with music services support such as Spotify, Deezer, Amazon Music, etc..."
LABEL org.opencontainers.image.version=${VERSION}
LABEL org.opencontainers.image.created=${BUILD_DATE}
LABEL org.opencontainers.image.documentation="https://github.com/smartgic/skill-sonos-controller"
LABEL org.opencontainers.image.source="https://github.com/smartgic/skill-sonos-controller"
LABEL org.opencontainers.image.vendor="Smart'Gic"

ARG ALPHA=false

RUN if [ "${ALPHA}" = "true" ]; then \
    python3 -m pip install --no-cache-dir git+https://github.com/smartgic/skill-sonos-controller.git; \
    else \
    python3 -m pip install --no-cache-dir skill-sonos-controller; \
    fi

ENTRYPOINT ["ovos-skill-launcher", "skill-sonos-controller.smartgic"]
