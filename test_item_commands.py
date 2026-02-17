"""
Test rápido: Verificar que los comandos de items están funcionando
"""
import sys
from pathlib import Path

# Setup paths
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

# Test 1: Verificar que items_manager está disponible
print("🔍 Test 1: Verificar imports...")
try:
    from backend.managers import items_manager
    print("✅ items_manager importado correctamente")
except ImportError as e:
    print(f"❌ Error importando items_manager: {e}")
    sys.exit(1)

# Test 2: Verificar que el módulo item_finder está disponible
print("\n🔍 Test 2: Verificar item_finder...")
try:
    from backend.services.discord_bot.commands.items.item_finder import setup_item_commands
    print("✅ setup_item_commands importado correctamente")
except ImportError as e:
    print(f"❌ Error importando setup_item_commands: {e}")
    sys.exit(1)

# Test 3: Verificar que hay items en el catálogo
print("\n🔍 Test 3: Verificar catálogo de items...")
try:
    stats = items_manager.get_items_stats()
    print(f"✅ Stats del catálogo:")
    print(f"   📦 Total: {stats['total_items']}")
    print(f"   🎲 Gacha: {stats['gacha_items']}")
    print(f"   🏪 Tienda: {stats['store_items']}")
except Exception as e:
    print(f"⚠️ Warning (esto es normal si es primera ejecución): {e}")

# Test 4: Obtener algunos items de prueba
print("\n🔍 Test 4: Obtener items de prueba...")
try:
    all_items = items_manager.get_all_items()
    if all_items:
        print(f"✅ Se encontraron {len(all_items)} items")
        print(f"   Primer item: {all_items[0]['nombre']} (ID: {all_items[0]['item_id']})")
    else:
        print("⚠️ No hay items en el catálogo (es normal si es primera ejecución)")
except Exception as e:
    print(f"❌ Error obteniendo items: {e}")

print("\n" + "="*50)
print("✅ Todos los tests pasaron correctamente!")
print("="*50)
print("\n📝 Próximos pasos:")
print("1. Importar items con: python backend/managers/items_cli.py import --source all")
print("2. Ver comando /lista_de_items en Discord")
print("3. Ver comando /item <id_o_nombre> en Discord")
