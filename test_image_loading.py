"""
test_image_loading.py

Verifica que las imágenes se cargan correctamente desde los items
"""
import sys
from pathlib import Path

# Setup paths
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from backend.managers import items_manager
from backend.services.discord_bot.commands.items.item_finder import _get_item_image_file, _create_item_embed

print("=" * 70)
print("🖼️ TEST: Carga de Imágenes de Items")
print("=" * 70)

# Obtener items
items = items_manager.get_all_items()

if not items:
    print("❌ No hay items disponibles")
    sys.exit(1)

print(f"\n📦 Total de items: {len(items)}\n")

# Verificar cada item
items_con_imagen = 0
items_sin_imagen = 0

for item in items:
    image_file = _get_item_image_file(item)
    imagen_local = item.get('imagen_local')
    
    status = "✅ CON IMAGEN" if image_file else "⚠️  SIN IMAGEN"
    
    print(f"{status}: {item['nombre']} (ID: {item['item_id']})")
    
    if imagen_local:
        print(f"        Ruta: {imagen_local}")
    
    if image_file:
        items_con_imagen += 1
        print(f"        Archivo: {image_file.filename}")
    else:
        items_sin_imagen += 1

print("\n" + "=" * 70)
print("📊 RESUMEN")
print("=" * 70)
print(f"Items con imagen: {items_con_imagen}")
print(f"Items sin imagen: {items_sin_imagen}")
print(f"Total: {len(items)}")

# Prueba de embed con imagen
print("\n" + "=" * 70)
print("🎨 PRUEBA DE EMBED")
print("=" * 70)

item_con_imagen = next((i for i in items if _get_item_image_file(i)), None)

if item_con_imagen:
    print(f"\n✅ Item con imagen encontrado: {item_con_imagen['nombre']}")
    
    embed = _create_item_embed(item_con_imagen)
    image_file = _get_item_image_file(item_con_imagen)
    
    print(f"   Embed title: {embed.title}")
    print(f"   Embed image URL: {embed.image.url if embed.image else 'None'}")
    print(f"   Discord File: {image_file.filename if image_file else 'None'}")
    
    if embed.image and image_file:
        print(f"\n   ✅ El embed está configurado para mostrar adjuntos")
        print(f"   ✅ El archivo se enviará como attachment")
        print(f"   ✅ Discord mostrará: {embed.image.url}")
    else:
        print(f"\n   ⚠️  El embed no tiene imagen configurada")
else:
    print(f"\n⚠️  No hay items con imagen para probar")

print("\n" + "=" * 70)
print("✅ Test completado")
print("=" * 70)

print("\n💡 Cómo funciona:")
print("   1. embed.set_image(url='attachment://item_image.png')")
print("   2. await interaction.response.send_message(embed=embed, file=image_file)")
print("   3. Discord mostrará la imagen en el embed automáticamente")
