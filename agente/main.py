"""Processo A2A separado do servidor MCP: python -m agente.main.

Um único worker escuta em 7300; o servidor MCP independente escuta em 7301.
As Tasks ficam apenas em memória e são perdidas ao reiniciar este processo.
"""

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run("agente.a2a_app:app", host="0.0.0.0", port=int(os.environ.get("A2A_PORT", "7300")), workers=1)
