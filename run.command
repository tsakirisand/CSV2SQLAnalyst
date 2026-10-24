#!/bin/zsh
cd -- "${0:A:h}"
uv sync
uv run streamlit run app.py --server.address 127.0.0.1 --server.port 8766
