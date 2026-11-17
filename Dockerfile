FROM odoo:18

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

USER odoo

# Forzar a Odoo a usar y crear las tablas en la base de datos configurada
CMD ["odoo", "-d", "odoo_supercharly", "--proxy-mode"]