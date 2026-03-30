#!/usr/bin/env python3
"""
Entry point para ejecutar el crawler de BCN Ley Chile.

Uso:
    python scripts/run_bcn_crawler.py
"""

import sys
from pathlib import Path

# Agregar src al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from crawlers.bcn_electric_crawler import main
import asyncio


if __name__ == "__main__":
    print("=" * 60)
    print("BCN Ley Chile - Crawler Normativa Eléctrica")
    print("=" * 60)
    print(f"\nDirectorio del proyecto: {project_root}")
    print("Nota: El navegador se abrirá en modo visible (headed)")
    print()

    asyncio.run(main())
