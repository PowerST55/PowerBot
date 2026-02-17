"""
Items Manager for PowerBot.
Gestiona el catálogo global de items desde assets.
Sistema de carga automática con reconocimiento de source (gacha/store).
"""
from __future__ import annotations
from datetime import datetime
from typing import Dict, Optional, List, Literal
from pathlib import Path
import json
import shutil
from backend.database import get_connection


# ============================================================
# CONFIGURACIÓN DE RUTAS
# ============================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Carpeta de assets (fuente de verdad)
ASSETS_ROOT = PROJECT_ROOT / "assets"
ASSETS_GACHA = ASSETS_ROOT / "gacha"
ASSETS_STORE = ASSETS_ROOT / "store"

# Carpeta de media procesada (runtime)
MEDIA_ROOT = PROJECT_ROOT / "media"
MEDIA_ITEMS = MEDIA_ROOT / "items"

# Niveles de rareza soportados
RARITY_LEVELS = ["common", "uncommon", "rare", "epic", "legendary"]

# Caché en memoria para consultas rápidas
_ITEMS_CACHE: Dict[int, Dict] = {}
_ITEMS_BY_KEY: Dict[str, Dict] = {}


# ============================================================
# INICIALIZACIÓN
# ============================================================

def _ensure_folders():
    """Crea las carpetas necesarias si no existen"""
    ASSETS_GACHA.mkdir(parents=True, exist_ok=True)
    ASSETS_STORE.mkdir(parents=True, exist_ok=True)
    MEDIA_ITEMS.mkdir(parents=True, exist_ok=True)
    
    # Crear carpetas de rareza
    for rarity in RARITY_LEVELS:
        (ASSETS_GACHA / rarity).mkdir(parents=True, exist_ok=True)


def _ensure_items_table(conn) -> None:
    """Crea la tabla de items con todos los campos necesarios"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_key TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            nombre TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            rareza TEXT NOT NULL,
            imagen_local TEXT,
            ataque INTEGER DEFAULT 0,
            defensa INTEGER DEFAULT 0,
            vida INTEGER DEFAULT 0,
            armadura INTEGER DEFAULT 0,
            mantenimiento INTEGER DEFAULT 0,
            metadata TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_source ON items(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_rareza ON items(rareza)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_key ON items(item_key)")
    
    conn.commit()


# ============================================================
# CACHÉ
# ============================================================

def _refresh_cache():
    """Recarga el caché de items desde la base de datos"""
    global _ITEMS_CACHE, _ITEMS_BY_KEY
    
    conn = get_connection()
    try:
        _ensure_items_table(conn)
        rows = conn.execute("SELECT * FROM items").fetchall()
        
        _ITEMS_CACHE.clear()
        _ITEMS_BY_KEY.clear()
        
        for row in rows:
            item = dict(row)
            _ITEMS_CACHE[item["item_id"]] = item
            _ITEMS_BY_KEY[item["item_key"]] = item
        
        return len(_ITEMS_CACHE)
    finally:
        conn.close()


def clear_cache():
    """Limpia el caché de items"""
    global _ITEMS_CACHE, _ITEMS_BY_KEY
    _ITEMS_CACHE.clear()
    _ITEMS_BY_KEY.clear()


# ============================================================
# IMPORTACIÓN DE ITEMS
# ============================================================

def _load_item_json(json_path: Path) -> Optional[Dict]:
    """Lee y valida un archivo item.json"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validar campos obligatorios
        required = ["item_key", "nombre", "descripcion", "rareza"]
        missing = [field for field in required if field not in data]
        
        if missing:
            print(f"❌ JSON inválido: faltan campos {missing}")
            return None
        
        return data
    except json.JSONDecodeError as e:
        print(f"❌ Error parseando JSON: {e}")
        return None
    except Exception as e:
        print(f"❌ Error leyendo JSON: {e}")
        return None


def _find_item_image(item_folder: Path) -> Optional[Path]:
    """Busca la imagen del item en varios formatos"""
    for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
        for name in ["icon", "image", "img"]:
            image_path = item_folder / f"{name}{ext}"
            if image_path.exists():
                return image_path
    return None


def _copy_item_image(image_path: Path, item_key: str) -> Optional[str]:
    """Copia la imagen a media/items/ y retorna la ruta relativa"""
    try:
        extension = image_path.suffix
        safe_name = item_key.replace(" ", "_").lower()
        dest_filename = f"{safe_name}{extension}"
        dest_path = MEDIA_ITEMS / dest_filename
        
        shutil.copy2(image_path, dest_path)
        return f"media/items/{dest_filename}"
    except Exception as e:
        print(f"⚠️ Error copiando imagen: {e}")
        return None


def import_item_from_folder(
    item_folder: Path,
    source: Literal["gacha", "store"]
) -> Optional[Dict]:
    """
    Importa un item desde una carpeta.
    
    Args:
        item_folder: Path a la carpeta del item
        source: Origen del item ("gacha" o "store")
        
    Returns:
        Dict con el item creado o None si falla
    """
    json_path = item_folder / "item.json"
    
    if not json_path.exists():
        print(f"⚠️ No se encontró item.json en {item_folder.name}")
        return None
    
    # Cargar JSON
    data = _load_item_json(json_path)
    if not data:
        return None
    
    # Buscar imagen
    image_path = _find_item_image(item_folder)
    imagen_local = None
    
    if image_path:
        imagen_local = _copy_item_image(image_path, data["item_key"])
        if imagen_local:
            print(f"  ✅ Imagen: {imagen_local}")
    else:
        print(f"  ⚠️ Sin imagen")
    
    # Extraer stats
    stats = data.get("stats", {})
    
    # Crear item en DB
    conn = get_connection()
    try:
        _ensure_items_table(conn)
        
        now_iso = datetime.utcnow().isoformat()
        
        # Verificar si ya existe
        existing = conn.execute(
            "SELECT item_id FROM items WHERE item_key = ?",
            (data["item_key"],)
        ).fetchone()
        
        if existing:
            print(f"  ⚠️ Item '{data['item_key']}' ya existe (ID: {existing['item_id']})")
            return get_item_by_id(existing["item_id"])
        
        # Insertar nuevo
        cursor = conn.execute(
            """INSERT INTO items (
                item_key, source, nombre, descripcion, rareza, imagen_local,
                ataque, defensa, vida, armadura, mantenimiento, metadata,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["item_key"],
                source,
                data["nombre"],
                data["descripcion"],
                data["rareza"],
                imagen_local,
                stats.get("ataque", 0),
                stats.get("defensa", 0),
                stats.get("vida", 0),
                stats.get("armadura", 0),
                stats.get("mantenimiento", 0),
                json.dumps(data.get("metadata", {})),
                now_iso,
                now_iso
            )
        )
        conn.commit()
        
        item_id = cursor.lastrowid
        item = get_item_by_id(item_id)
        
        # Actualizar caché
        if item:
            _ITEMS_CACHE[item_id] = item
            _ITEMS_BY_KEY[data["item_key"]] = item
        
        print(f"  ✅ Item creado: '{data['nombre']}' (ID: {item_id})")
        return item
        
    except Exception as e:
        conn.rollback()
        print(f"  ❌ Error guardando item: {e}")
        return None
    finally:
        conn.close()


def import_gacha_items() -> Dict[str, any]:
    """
    Importa todos los items de gacha desde assets/items/gacha/.
    
    Returns:
        Dict con estadísticas de importación
    """
    _ensure_folders()
    
    results = {
        "total": 0,
        "successful": 0,
        "failed": 0,
        "by_rarity": {rarity: 0 for rarity in RARITY_LEVELS}
    }
    
    print("\n" + "=" * 60)
    print("📦 IMPORTANDO ITEMS DE GACHA")
    print("=" * 60)
    
    for rarity in RARITY_LEVELS:
        rarity_folder = ASSETS_GACHA / rarity
        
        if not rarity_folder.exists():
            continue
        
        item_folders = [f for f in rarity_folder.iterdir() if f.is_dir()]
        
        if not item_folders:
            continue
        
        print(f"\n📂 Rareza: {rarity.upper()} ({len(item_folders)} items)")
        print("-" * 60)
        
        for item_folder in item_folders:
            results["total"] += 1
            print(f"  📦 {item_folder.name}")
            
            item = import_item_from_folder(item_folder, "gacha")
            
            if item:
                results["successful"] += 1
                results["by_rarity"][rarity] += 1
            else:
                results["failed"] += 1
    
    print("\n" + "=" * 60)
    print("✅ RESUMEN DE IMPORTACIÓN - GACHA")
    print("=" * 60)
    print(f"Total procesados: {results['total']}")
    print(f"Exitosos: {results['successful']}")
    print(f"Fallidos: {results['failed']}")
    print("\nPor rareza:")
    for rarity, count in results["by_rarity"].items():
        if count > 0:
            print(f"  {rarity.capitalize()}: {count}")
    
    return results


def import_store_items() -> Dict[str, any]:
    """
    Importa todos los items de tienda desde assets/items/store/.
    
    Returns:
        Dict con estadísticas de importación
    """
    _ensure_folders()
    
    results = {
        "total": 0,
        "successful": 0,
        "failed": 0
    }
    
    print("\n" + "=" * 60)
    print("🏪 IMPORTANDO ITEMS DE TIENDA")
    print("=" * 60)
    
    if not ASSETS_STORE.exists():
        print("⚠️ No existe la carpeta de tienda")
        return results
    
    item_folders = [f for f in ASSETS_STORE.iterdir() if f.is_dir()]
    
    if not item_folders:
        print("⚠️ No hay items en la tienda")
        return results
    
    print(f"\n📂 Procesando {len(item_folders)} items...")
    print("-" * 60)
    
    for item_folder in item_folders:
        results["total"] += 1
        print(f"  🏪 {item_folder.name}")
        
        item = import_item_from_folder(item_folder, "store")
        
        if item:
            results["successful"] += 1
        else:
            results["failed"] += 1
    
    print("\n" + "=" * 60)
    print("✅ RESUMEN DE IMPORTACIÓN - TIENDA")
    print("=" * 60)
    print(f"Total procesados: {results['total']}")
    print(f"Exitosos: {results['successful']}")
    print(f"Fallidos: {results['failed']}")
    
    return results


def import_all_items() -> Dict[str, any]:
    """
    Importa TODOS los items (gacha + tienda).
    
    Returns:
        Dict con estadísticas completas
    """
    gacha_results = import_gacha_items()
    store_results = import_store_items()
    
    # Refrescar caché
    cached = _refresh_cache()
    
    total_results = {
        "gacha": gacha_results,
        "store": store_results,
        "total_items": gacha_results["total"] + store_results["total"],
        "total_successful": gacha_results["successful"] + store_results["successful"],
        "total_failed": gacha_results["failed"] + store_results["failed"],
        "cached_items": cached
    }
    
    print("\n" + "=" * 60)
    print("🎉 IMPORTACIÓN COMPLETA")
    print("=" * 60)
    print(f"Total procesados: {total_results['total_items']}")
    print(f"Exitosos: {total_results['total_successful']}")
    print(f"Fallidos: {total_results['total_failed']}")
    print(f"Items en caché: {total_results['cached_items']}")
    
    return total_results


# ============================================================
# CONSULTAS DE ITEMS
# ============================================================

def get_item_by_id(item_id: int) -> Optional[Dict]:
    """
    Obtiene un item por su ID (usa caché).
    
    Args:
        item_id: ID del item
        
    Returns:
        Dict con el item o None
    """
    # Intentar desde caché
    if item_id in _ITEMS_CACHE:
        return _ITEMS_CACHE[item_id].copy()
    
    # Consultar DB
    conn = get_connection()
    try:
        _ensure_items_table(conn)
        row = conn.execute(
            "SELECT * FROM items WHERE item_id = ?",
            (item_id,)
        ).fetchone()
        
        if row:
            item = dict(row)
            _ITEMS_CACHE[item_id] = item
            return item.copy()
        
        return None
    finally:
        conn.close()


def get_item_by_key(item_key: str) -> Optional[Dict]:
    """
    Obtiene un item por su key único (usa caché).
    
    Args:
        item_key: Key del item (ej: "sword_basic_001")
        
    Returns:
        Dict con el item o None
    """
    # Intentar desde caché
    if item_key in _ITEMS_BY_KEY:
        return _ITEMS_BY_KEY[item_key].copy()
    
    # Consultar DB
    conn = get_connection()
    try:
        _ensure_items_table(conn)
        row = conn.execute(
            "SELECT * FROM items WHERE item_key = ?",
            (item_key,)
        ).fetchone()
        
        if row:
            item = dict(row)
            _ITEMS_BY_KEY[item_key] = item
            _ITEMS_CACHE[item["item_id"]] = item
            return item.copy()
        
        return None
    finally:
        conn.close()


def get_all_items(source: Optional[str] = None) -> List[Dict]:
    """
    Obtiene todos los items.
    
    Args:
        source: Filtrar por source ("gacha", "store") o None para todos
        
    Returns:
        Lista de items
    """
    conn = get_connection()
    try:
        _ensure_items_table(conn)
        
        if source:
            rows = conn.execute(
                "SELECT * FROM items WHERE source = ? ORDER BY rareza DESC, nombre ASC",
                (source,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM items ORDER BY source ASC, rareza DESC, nombre ASC"
            ).fetchall()
        
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_items_by_rareza(rareza: str, source: Optional[str] = None) -> List[Dict]:
    """
    Obtiene items por rareza.
    
    Args:
        rareza: Nivel de rareza
        source: Filtrar por source o None
        
    Returns:
        Lista de items
    """
    conn = get_connection()
    try:
        _ensure_items_table(conn)
        
        if source:
            rows = conn.execute(
                "SELECT * FROM items WHERE rareza = ? AND source = ? ORDER BY nombre ASC",
                (rareza, source)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM items WHERE rareza = ? ORDER BY nombre ASC",
                (rareza,)
            ).fetchall()
        
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_gacha_items() -> List[Dict]:
    """Obtiene todos los items de gacha"""
    return get_all_items(source="gacha")


def get_store_items() -> List[Dict]:
    """Obtiene todos los items de tienda"""
    return get_all_items(source="store")


def get_item_image_path(item_id: int) -> Optional[Path]:
    """
    Obtiene la ruta absoluta de la imagen de un item.
    
    Args:
        item_id: ID del item
        
    Returns:
        Path absoluto o None
    """
    item = get_item_by_id(item_id)
    if not item or not item.get("imagen_local"):
        return None
    
    return PROJECT_ROOT / item["imagen_local"]


def get_items_stats() -> Dict[str, any]:
    """
    Obtiene estadísticas del catálogo de items.
    
    Returns:
        Dict con estadísticas completas
    """
    conn = get_connection()
    try:
        _ensure_items_table(conn)
        
        # Total por source
        gacha_count = conn.execute(
            "SELECT COUNT(*) as count FROM items WHERE source = 'gacha'"
        ).fetchone()["count"]
        
        store_count = conn.execute(
            "SELECT COUNT(*) as count FROM items WHERE source = 'store'"
        ).fetchone()["count"]
        
        # Por rareza
        rarity_stats = {}
        for rarity in RARITY_LEVELS:
            count = conn.execute(
                "SELECT COUNT(*) as count FROM items WHERE rareza = ?",
                (rarity,)
            ).fetchone()["count"]
            rarity_stats[rarity] = count
        
        return {
            "total_items": gacha_count + store_count,
            "gacha_items": gacha_count,
            "store_items": store_count,
            "by_rarity": rarity_stats,
            "cached_items": len(_ITEMS_CACHE)
        }
    finally:
        conn.close()


# ============================================================
# UTILIDADES
# ============================================================

def create_item_template(
    item_key: str,
    source: Literal["gacha", "store"],
    rareza: str = "common"
) -> bool:
    """
    Crea una carpeta template para un nuevo item.
    
    Args:
        item_key: Key único del item
        source: "gacha" o "store"
        rareza: Nivel de rareza (solo para gacha)
        
    Returns:
        True si se creó exitosamente
    """
    _ensure_folders()
    
    # Determinar carpeta destino
    if source == "gacha":
        if rareza not in RARITY_LEVELS:
            print(f"❌ Rareza '{rareza}' inválida. Use: {', '.join(RARITY_LEVELS)}")
            return False
        item_folder = ASSETS_GACHA / rareza / item_key
    else:
        item_folder = ASSETS_STORE / item_key
    
    if item_folder.exists():
        print(f"⚠️ La carpeta '{item_key}' ya existe")
        return False
    
    try:
        item_folder.mkdir(parents=True)
        
        # Template JSON
        template = {
            "item_key": item_key,
            "nombre": "Nombre del Item",
            "descripcion": "Descripción detallada del item",
            "rareza": rareza if source == "gacha" else "common",
            "stats": {
                "ataque": 0,
                "defensa": 0,
                "vida": 0,
                "armadura": 0,
                "mantenimiento": 0
            },
            "metadata": {
                "categoria": "weapon",
                "tipo": "sword",
                "peso": 1,
                "precio_tienda": 100 if source == "store" else None,
                "vendible": True,
                "tradeable": True,
                "stackable": False
            }
        }
        
        json_file = item_folder / "item.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Template creado en: {item_folder}")
        print(f"📝 Edita: {json_file}")
        print(f"🖼️ Agrega una imagen llamada 'icon.png'")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creando template: {e}")
        return False


def validate_item_structure() -> Dict[str, List[str]]:
    """
    Valida la estructura de carpetas de assets.
    
    Returns:
        Dict con items válidos e inválidos
    """
    _ensure_folders()
    
    valid = []
    invalid = []
    
    # Validar gacha
    for rarity in RARITY_LEVELS:
        rarity_folder = ASSETS_GACHA / rarity
        if not rarity_folder.exists():
            continue
        
        for item_folder in rarity_folder.iterdir():
            if not item_folder.is_dir():
                continue
            
            json_path = item_folder / "item.json"
            if json_path.exists():
                valid.append(f"gacha/{rarity}/{item_folder.name}")
            else:
                invalid.append(f"gacha/{rarity}/{item_folder.name} (sin item.json)")
    
    # Validar store
    if ASSETS_STORE.exists():
        for item_folder in ASSETS_STORE.iterdir():
            if not item_folder.is_dir():
                continue
            
            json_path = item_folder / "item.json"
            if json_path.exists():
                valid.append(f"store/{item_folder.name}")
            else:
                invalid.append(f"store/{item_folder.name} (sin item.json)")
    
    return {
        "valid": valid,
        "invalid": invalid,
        "total_valid": len(valid),
        "total_invalid": len(invalid)
    }
