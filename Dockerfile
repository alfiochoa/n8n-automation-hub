# n8n pinned to an exact version: upgrades are a deliberate commit, never a surprise at 3 a.m.
FROM n8nio/n8n:1.123.84

USER root
RUN mkdir -p /opt/hub && chown node:node /opt/hub
USER node
WORKDIR /opt/hub
COPY --chown=node:node workflows ./workflows
COPY --chown=node:node scripts/start.sh scripts/provision.sh scripts/provision_credentials.js scripts/activate_workflows.js \
     scripts/bootstrap_owner.js scripts/gate.js ./scripts/
COPY --chown=node:node config ./config

# Non-secret defaults. Secrets (N8N_ENCRYPTION_KEY, DB_POSTGRESDB_*, N8N_OWNER_PASSWORD, LLM_API_KEY, HUB_NOTIFY_URL) are injected by the platform.
ENV NODE_ENV=production \
    DB_TYPE=postgresdb \
    DB_POSTGRESDB_SCHEMA=n8n \
    DB_POSTGRESDB_DATABASE=postgres \
    DB_POSTGRESDB_PORT=5432 \
    DB_POSTGRESDB_SSL_ENABLED=true \
    DB_POSTGRESDB_SSL_REJECT_UNAUTHORIZED=false \
    N8N_PROTOCOL=https \
    N8N_PROXY_HOPS=1 \
    N8N_SECURE_COOKIE=true \
    N8N_DIAGNOSTICS_ENABLED=false \
    N8N_PERSONALIZATION_ENABLED=false \
    N8N_VERSION_NOTIFICATIONS_ENABLED=false \
    N8N_TEMPLATES_ENABLED=false \
    N8N_HIRING_BANNER_ENABLED=false \
    N8N_RUNNERS_ENABLED=false \
    N8N_PUBLIC_API_DISABLED=true \
    N8N_DISABLE_UI=true \
    N8N_PAYLOAD_SIZE_MAX=1 \
    N8N_BLOCK_ENV_ACCESS_IN_NODE=false \
    NODE_FUNCTION_ALLOW_BUILTIN=crypto \
    EXECUTIONS_DATA_PRUNE=true \
    EXECUTIONS_DATA_MAX_AGE=48 \
    EXECUTIONS_DATA_PRUNE_MAX_COUNT=500 \
    GENERIC_TIMEZONE=Europe/Madrid \
    TZ=Europe/Madrid \
    HUB_LEAN=true \
    HUB_CHAOS=false \
    N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=false

EXPOSE 10000
# tini (from the base image) reaps zombies and forwards signals. start.sh keeps the public port closed until the owner account is claimed.
ENTRYPOINT ["tini", "--"]
CMD ["sh", "/opt/hub/scripts/start.sh"]
