#!/usr/bin/env python3
"""
PowerBot Startup Script - Single entry point for VPS deployment
Ejecuta desde raíz: python start.py

✓ Detecta y usa automáticamente el venv si existe
✓ Si no hay venv, usa el Python global del sistema
"""

import subprocess
import sys
from pathlib import Path

# Obtener la raíz del proyecto
PROJECT_ROOT = Path(__file__).parent

# Configurar el path para importar correctamente
sys.path.insert(0, str(PROJECT_ROOT))

def main():
    """Inicia PowerBot"""
    try:
        # 1. IMPORTANTE: Re-ejecutar en venv si existe
        #    Esto asegura que usamos las dependencias del venv
        from backend.bootstrap import _reexec_in_venv
        _reexec_in_venv(None, ".venv")
        
        # Si llegamos aquí, ya estamos en el venv (o no existe)
        import asyncio
        import logging
        
        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
        )
        
        # 2. Importar y ejecutar app.py
        from backend.app import main as app_main
        
        exit_code = asyncio.run(app_main())
        sys.exit(exit_code if isinstance(exit_code, int) else 1)
        
    except KeyboardInterrupt:
        print("\n✓ PowerBot detenido")
        sys.exit(130)
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
