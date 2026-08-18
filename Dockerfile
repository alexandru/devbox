FROM ubuntu:26.04

ARG USER_UID="1000"
ARG USER_GID="1000"
ARG NODE_MAJOR="24"

ENV DEBIAN_FRONTEND=noninteractive
ENV SDKMAN_DIR=/opt/sdkman
ENV SHELL=/bin/bash

# Base system
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        binutils \
        bsdextrautils \
        ca-certificates \
        curl \
        direnv \
        fd-find \
        file \
        git \
        jq \
        iproute2 \
        iptables \
        gnupg \
        less \
        make \
        neovim \
        openssh-client \
        patch \
        procps \
        ripgrep \
        sudo \
        tar \
        tree \
        unzip \
        wget \
        wireguard-tools \
        zip && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /tmp/*

RUN ln -s /usr/bin/fdfind /usr/local/bin/fd

# Language runtimes
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" > /etc/apt/sources.list.d/nodesource.list

RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs openjdk-21-jdk-headless && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /tmp/*

# GitHub SSH host key
RUN mkdir -p /etc/ssh/ssh_known_hosts.d && \
    ssh-keyscan github.com > /etc/ssh/ssh_known_hosts

# JVM build tools
RUN curl -fsSL "https://get.sdkman.io?ci=true&rcupdate=false" | bash && \
    sed -i 's/^sdkman_auto_env=.*/sdkman_auto_env=true/' "$SDKMAN_DIR/etc/config"

RUN bash -c 'source "$SDKMAN_DIR/bin/sdkman-init.sh" && \
        sdk install maven && \
        sdk install sbt && \
        sdk install scalacli && \
        sdk install gradle' && \
    rm -rf "$SDKMAN_DIR/tmp"/*

RUN curl -fLo /usr/local/bin/cs https://github.com/coursier/launchers/raw/master/coursier && \
    chmod 0755 /usr/local/bin/cs

# Development user
RUN if getent group "$USER_GID" >/dev/null; then \
        existing_group="$(getent group "$USER_GID" | cut -d: -f1)"; \
        if [ "$existing_group" != "dev" ]; then \
            groupmod -n dev "$existing_group"; \
        fi; \
    else \
        groupadd -g "$USER_GID" dev; \
    fi

RUN if getent passwd "$USER_UID" >/dev/null; then \
        existing_user="$(getent passwd "$USER_UID" | cut -d: -f1)"; \
        if [ "$existing_user" != "dev" ]; then \
            usermod -l dev "$existing_user"; \
        fi; \
        usermod -d /home/dev -m -s /bin/bash -g dev dev; \
    else \
        useradd -m -s /bin/bash -g dev -u "$USER_UID" dev; \
    fi

RUN echo "dev ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/dev && \
    chmod 0440 /etc/sudoers.d/dev

RUN mkdir -p /workspaces /home/dev/.config && \
    chown -R dev:dev /opt/sdkman /workspaces /home/dev

ENV HOME=/home/dev
ENV PATH="/home/dev/bin:/home/dev/.local/bin:/home/dev/.opencode/bin:/home/dev/.local/share/coursier/bin:/usr/local/bin:${PATH}"

# Container helper scripts
COPY bin/devbox-entrypoint /usr/local/bin/devbox-entrypoint
COPY bin/devbox-install-user-files /usr/local/bin/devbox-install-user-files
COPY bin/osc52-clipboard /usr/local/bin/osc52-clipboard
COPY bin/resolvconf /usr/local/bin/resolvconf
COPY bin/update-all /usr/local/share/devbox/update-all
COPY home/.devboxrc /usr/local/share/devbox/devboxrc

RUN chmod 0755 \
    /usr/local/bin/devbox-entrypoint \
    /usr/local/bin/devbox-install-user-files \
    /usr/local/bin/osc52-clipboard \
    /usr/local/bin/resolvconf

# Seed managed user files into the image and persistent home volume.
RUN devbox-install-user-files

# Route common clipboard commands through OSC 52.
RUN ln -sf /usr/local/bin/osc52-clipboard /usr/local/bin/wl-copy && \
    ln -sf /usr/local/bin/osc52-clipboard /usr/local/bin/xclip && \
    ln -sf /usr/local/bin/osc52-clipboard /usr/local/bin/xsel

# User-scoped tools
WORKDIR /home/dev
USER dev

RUN curl -fsSL https://opencode.ai/install \
    | bash -s -- --no-modify-path && \
    opencode --version

RUN curl -fsSL https://raw.githubusercontent.com/anomalyco/opencode/v2/install \
    | bash -s -- --no-modify-path && \
    opencode2 --version

RUN npm install -g --prefix "$HOME/.local" --ignore-scripts @earendil-works/pi-coding-agent && \
    npm install -g --prefix "$HOME/.local" @github/copilot && \
    pi --version && \
    copilot --version

# Pre-create common JVM tool directories so mounted files don't force root-owned parent creation.
RUN mkdir -p \
    /home/dev/.sbt/1.0 \
    /home/dev/.m2 \
    /home/dev/.gradle \
    /home/dev/.config/sbt/2

# Keep image copies available to seed retained home volumes that predate user-scoped installation.
USER root
RUN install -d -m 0755 /usr/local/share/devbox/bin && \
    install -m 0755 /home/dev/.opencode/bin/opencode /usr/local/share/devbox/bin/opencode

USER dev
RUN cs install --contrib cellar && \
    cellar telemetry disable

# Runtime
VOLUME ["/home/dev"]
EXPOSE 10012
ENTRYPOINT ["/usr/local/bin/devbox-entrypoint"]
CMD ["bash"]
