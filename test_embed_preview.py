"""
test_embed_preview.py

Genera vista previa de cómo se ven los embeds de items en Discord
(Para referencia visual únicamente)
"""
import sys
from pathlib import Path

# Setup paths
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from backend.managers import items_manager
from backend.services.discord_bot.commands.items.item_finder import _create_item_embed

print("=" * 70)
print("🎨 VISTA PREVIA DE EMBEDS DE ITEMS")
print("=" * 70)

# Obtener algunos items de ejemplo
items = items_manager.get_all_items()

if not items:
    print("❌ No hay items disponibles")
    print("Ejecuta: python backend/managers/items_cli.py import --source all")
    sys.exit(1)

# Mostrar 3 items de diferentes raridades como ejemplo
print("\n📋 Embeds de Ejemplo:\n")

for i, item in enumerate(items[:3], 1):
    embed = _create_item_embed(item)
    
    print(f"\n{'─' * 70}")
    print(f"EJEMPLO {i}: {item['nombre']}")
    print(f"{'─' * 70}")
    
    # Simular visualización de embed
    print(f"\n📌 Título: {embed.title}")
    print(f"📝 Descripción: {embed.description[:100]}...")
    print(f"🎨 Color: {embed.color}")
    
    # Mostrar campos
    for field in embed.fields:
        print(f"\n  🏷️  {field.name}")
        print(f"     {field.value.replace(chr(10), chr(10) + '     ')}")
    
    if embed.footer:
        print(f"\n  📍 Footer: {embed.footer.text}")

print("\n" + "=" * 70)
print("✅ Vista previa completada")
print("=" * 70)
print("\n💡 Estos embeds se mostrarán en Discord cuando uses:")
print("   /item <id_o_nombre>")
print("   o selecciones un item del menú en /lista_de_items")
