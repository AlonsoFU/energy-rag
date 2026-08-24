#!/bin/bash
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
exec env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin \
  WRITE=1 LIMIT=0 PYTHONPATH=. \
  venv/bin/python -m scripts.scrape_vinculaciones
