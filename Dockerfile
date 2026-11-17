FROM odoo:18

USER root

# Instalar dependencias adicionales si las necesitas (opcional)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

USER odoo