FROM surfbench-runtime:0.1.1
ARG CLAUDE_VERSION=2.1.314
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_VERSION} && claude --version
COPY fixture_store.py /opt/client/surfbench/fixture_store.py
COPY data/ /opt/surfbench-data/
COPY protected/ /protected/
RUN chmod 700 /protected /opt/surfbench-data && chmod 755 /protected/entrypoint.sh /protected/collect.sh
ENTRYPOINT ["/protected/entrypoint.sh"]
