FROM python:3.11-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp_operadora/ ./mcp_operadora/
ENV MCP_OPERADORA_HOST=0.0.0.0 \
    MCP_OPERADORA_PORT=9000 \
    MCP_OPERADORA_DADOS=/dados
EXPOSE 9000
CMD ["python", "-m", "mcp_operadora.server"]
