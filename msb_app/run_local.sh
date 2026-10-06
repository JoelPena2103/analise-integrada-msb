#!/bin/bash
# Arranca a app Streamlit (Ubuntu/WSL).
# Uso: ./run_local.sh   (ou: bash run_local.sh)

# Vai sempre para a pasta onde este script está guardado.
cd "$(dirname "$0")" || exit 1

# Usa o Python do .venv diretamente (não depende do "activate" nem do PATH).
PY=".venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "O ambiente virtual (.venv) não existe ou está danificado nesta pasta."
  echo "Recrie-o com:"
  echo "  rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if ! "$PY" -c "import streamlit" 2>/dev/null; then
  echo "O Streamlit não está instalado neste .venv."
  echo "Instale com:  .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# Aviso (não bloqueia) se o Postgres local não estiver a responder.
if command -v pg_isready >/dev/null 2>&1; then
  if ! pg_isready -q -h localhost -p 5432; then
    echo "Aviso: o Postgres não responde em localhost:5432."
    echo "Arranque-o com:  sudo service postgresql start"
  fi
fi

echo "A iniciar a app... (Ctrl+C para parar)"
exec "$PY" -m streamlit run app.py --server.headless true
