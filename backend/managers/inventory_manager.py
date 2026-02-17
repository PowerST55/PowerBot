"""
Inventory Manager for PowerBot.
Gestiona inventarios de usuarios (posesión de items).
"""
from __future__ import annotations
from datetime import datetime
from typing import Dict, Optional, List
from backend.database import get_connection
from backend.managers import items_manager


def _ensure_inventory_tables(conn) -> None:
    """Crea la tabla de inventario de usuarios"""
    
    # Tabla de inventario de usuarios
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            acquired_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
            UNIQUE(user_id, item_id)
        )
        """
    )
    
    # Índices para optimización
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_inventory_user ON user_inventory(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_inventory_item ON user_inventory(item_id)")
    
    conn.commit()


# ============================================================
# GESTIÓN DE INVENTARIO DE USUARIOS
# ============================================================

def add_item_to_user(
    user_id: int,
    item_id: int,
    quantity: int = 1
) -> Dict[str, any]:
    """
    Añade un item al inventario de un usuario.
    
    Args:
        user_id: ID universal del usuario
        item_id: ID del item a añadir
        quantity: Cantidad a añadir (default 1)
        
    Returns:
        Dict con resultado de la operación:
            - success: bool
            - message: str
            - total_quantity: int (cantidad total después de añadir)
            - item: Dict (información del item)
    """
    if quantity <= 0:
        return {
            "success": False,
            "message": "Cantidad debe ser mayor a 0",
            "total_quantity": 0,
            "item": None
        }
    
    conn = get_connection()
    try:
        _ensure_inventory_tables(conn)
        conn.execute("BEGIN IMMEDIATE")
        
        # Verificar que el item existe (usa items_manager)
        item = items_manager.get_item_by_id(item_id)
        if not item:
            conn.rollback()
            return {
                "success": False,
                "message": f"Item con ID {item_id} no existe",
                "total_quantity": 0,
                "item": None
            }
        
        # Verificar que el usuario existe
        user_check = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        
        if not user_check:
            conn.rollback()
            return {
                "success": False,
                "message": f"Usuario con ID {user_id} no existe",
                "total_quantity": 0,
                "item": None
            }
        
        now_iso = datetime.utcnow().isoformat()
        
        # Verificar si el usuario ya tiene este item
        existing = conn.execute(
            "SELECT quantity FROM user_inventory WHERE user_id = ? AND item_id = ?",
            (user_id, item_id)
        ).fetchone()
        
        if existing:
            # Actualizar cantidad existente
            new_quantity = existing["quantity"] + quantity
            conn.execute(
                "UPDATE user_inventory SET quantity = ?, updated_at = ? WHERE user_id = ? AND item_id = ?",
                (new_quantity, now_iso, user_id, item_id)
            )
            total = new_quantity
        else:
            # Insertar nuevo item en inventario
            conn.execute(
                """INSERT INTO user_inventory (user_id, item_id, quantity, acquired_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, item_id, quantity, now_iso, now_iso)
            )
            total = quantity
        
        conn.commit()
        
        return {
            "success": True,
            "message": f"Se añadieron {quantity} x {item['nombre']} al inventario",
            "total_quantity": total,
            "item": item
        }
        
    except Exception as e:
        conn.rollback()
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "total_quantity": 0,
            "item": None
        }
    finally:
        conn.close()


def get_user_inventory(user_id: int) -> List[Dict]:
    """
    Obtiene todo el inventario de un usuario con información completa de items.
    
    Args:
        user_id: ID universal del usuario
        
    Returns:
        Lista de dicts con items del inventario incluyendo cantidad y stats
        
    Example:
        >>> inventario = get_user_inventory(42)
        >>> for item in inventario:
        ...     print(f"{item['nombre']} x{item['quantity']} - ATK:{item['ataque']} DEF:{item['defensa']}")
    """
    conn = get_connection()
    try:
        _ensure_inventory_tables(conn)
        # Asegurar que la tabla items exista
        items_manager._ensure_items_table(conn)
        
        rows = conn.execute(
            """SELECT 
                   i.item_id, i.item_key, i.source, i.nombre, i.descripcion, i.rareza,
                   i.imagen_local, i.ataque, i.defensa, i.vida, i.armadura, i.mantenimiento,
                   i.metadata, ui.quantity, ui.acquired_at, ui.updated_at
               FROM user_inventory ui
               JOIN items i ON ui.item_id = i.item_id
               WHERE ui.user_id = ?
               ORDER BY i.rareza DESC, i.nombre ASC""",
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def remove_item_from_user(
    user_id: int,
    item_id: int,
    quantity: int = 1
) -> Dict[str, any]:
    """
    Remueve un item del inventario de un usuario.
    
    Args:
        user_id: ID universal del usuario
        item_id: ID del item a remover
        quantity: Cantidad a remover (default 1)
        
    Returns:
        Dict con resultado de la operación
    """
    if quantity <= 0:
        return {
            "success": False,
            "message": "Cantidad debe ser mayor a 0",
            "remaining_quantity": 0
        }
    
    conn = get_connection()
    try:
        _ensure_inventory_tables(conn)
        conn.execute("BEGIN IMMEDIATE")
        
        # Verificar que el item existe
        item = items_manager.get_item_by_id(item_id)
        if not item:
            conn.rollback()
            return {
                "success": False,
                "message": f"Item con ID {item_id} no existe",
                "remaining_quantity": 0
            }
        
        # Verificar cantidad actual
        existing = conn.execute(
            "SELECT quantity FROM user_inventory WHERE user_id = ? AND item_id = ?",
            (user_id, item_id)
        ).fetchone()
        
        if not existing:
            conn.rollback()
            return {
                "success": False,
                "message": f"Usuario no tiene el item '{item['nombre']}'",
                "remaining_quantity": 0
            }
        
        if existing["quantity"] < quantity:
            conn.rollback()
            return {
                "success": False,
                "message": f"Cantidad insuficiente. Tiene {existing['quantity']}, intenta remover {quantity}",
                "remaining_quantity": existing["quantity"]
            }
        
        now_iso = datetime.utcnow().isoformat()
        new_quantity = existing["quantity"] - quantity
        
        if new_quantity == 0:
            # Eliminar del inventario
            conn.execute(
                "DELETE FROM user_inventory WHERE user_id = ? AND item_id = ?",
                (user_id, item_id)
            )
        else:
            # Actualizar cantidad
            conn.execute(
                "UPDATE user_inventory SET quantity = ?, updated_at = ? WHERE user_id = ? AND item_id = ?",
                (new_quantity, now_iso, user_id, item_id)
            )
        
        conn.commit()
        
        return {
            "success": True,
            "message": f"Se removieron {quantity} x {item['nombre']} del inventario",
            "remaining_quantity": new_quantity,
            "item": item
        }
        
    except Exception as e:
        conn.rollback()
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "remaining_quantity": 0
        }
    finally:
        conn.close()


def get_user_item_quantity(user_id: int, item_id: int) -> int:
    """
    Obtiene la cantidad de un item específico que tiene un usuario.
    
    Args:
        user_id: ID universal del usuario
        item_id: ID del item
        
    Returns:
        Cantidad del item (0 si no lo tiene)
    """
    conn = get_connection()
    try:
        _ensure_inventory_tables(conn)
        row = conn.execute(
            "SELECT quantity FROM user_inventory WHERE user_id = ? AND item_id = ?",
            (user_id, item_id)
        ).fetchone()
        
        return row["quantity"] if row else 0
    finally:
        conn.close()


def user_has_item(user_id: int, item_id: int) -> bool:
    """
    Verifica si un usuario tiene un item específico.
    
    Args:
        user_id: ID universal del usuario
        item_id: ID del item
        
    Returns:
        True si tiene al menos 1, False si no
    """
    return get_user_item_quantity(user_id, item_id) > 0


def get_inventory_stats(user_id: int) -> Dict[str, any]:
    """
    Obtiene estadísticas agregadas del inventario de un usuario.
    
    Args:
        user_id: ID universal del usuario
        
    Returns:
        Dict con estadísticas:
            - total_items: int (tipos únicos de items)
            - total_quantity: int (cantidad total sumando todos)
            - stats_totales: Dict (suma de todos los stats)
    """
    conn = get_connection()
    try:
        _ensure_inventory_tables(conn)
        # Asegurar que la tabla items exista
        items_manager._ensure_items_table(conn)
        
        # Total de items únicos y cantidad total
        count_row = conn.execute(
            """SELECT COUNT(*) as unique_items, SUM(quantity) as total_quantity
               FROM user_inventory WHERE user_id = ?""",
            (user_id,)
        ).fetchone()
        
        # Suma de stats de todos los items
        stats_row = conn.execute(
            """SELECT 
                   SUM(i.ataque * ui.quantity) as ataque_total,
                   SUM(i.defensa * ui.quantity) as defensa_total,
                   SUM(i.vida * ui.quantity) as vida_total,
                   SUM(i.armadura * ui.quantity) as armadura_total,
                   SUM(i.mantenimiento * ui.quantity) as mantenimiento_total
               FROM user_inventory ui
               JOIN items i ON ui.item_id = i.item_id
               WHERE ui.user_id = ?""",
            (user_id,)
        ).fetchone()
        
        return {
            "total_items": count_row["unique_items"] or 0,
            "total_quantity": count_row["total_quantity"] or 0,
            "stats_totales": {
                "ataque": stats_row["ataque_total"] or 0,
                "defensa": stats_row["defensa_total"] or 0,
                "vida": stats_row["vida_total"] or 0,
                "armadura": stats_row["armadura_total"] or 0,
                "mantenimiento": stats_row["mantenimiento_total"] or 0
            }
        }
    finally:
        conn.close()


def clear_user_inventory(user_id: int) -> Dict[str, any]:
    """
    Limpia completamente el inventario de un usuario.
    
    Args:
        user_id: ID universal del usuario
        
    Returns:
        Dict con resultado de la operación
        
    Warning:
        Esta operación es IRREVERSIBLE
    """
    conn = get_connection()
    try:
        _ensure_inventory_tables(conn)
        
        # Contar items antes de borrar
        count = conn.execute(
            "SELECT COUNT(*) as count FROM user_inventory WHERE user_id = ?",
            (user_id,)
        ).fetchone()["count"]
        
        if count == 0:
            return {
                "success": True,
                "message": "El inventario ya estaba vacío",
                "items_removed": 0
            }
        
        # Eliminar todos los items
        conn.execute(
            "DELETE FROM user_inventory WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        
        return {
            "success": True,
            "message": f"Inventario limpiado. Se removieron {count} tipos de items",
            "items_removed": count
        }
        
    except Exception as e:
        conn.rollback()
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "items_removed": 0
        }
    finally:
        conn.close()
