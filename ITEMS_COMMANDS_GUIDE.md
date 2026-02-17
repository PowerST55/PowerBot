# 📦 Comandos de Items - Guía de Uso

## ✅ Comandos Disponibles

### 1️⃣ `/lista_de_items`
Muestra todos los items disponibles en el catálogo con un selector interactivo.

**Uso:**
```
/lista_de_items
/lista_de_items source:gacha     # Solo items de gacha
/lista_de_items source:store     # Solo items de tienda
```

**Características:**
- 📊 Muestra estadísticas del catálogo (total, gacha, tienda)
- 🎯 Select menu para elegir item directamente
- 🌟 Información de rareza con emojis (⚪🟢🔵🟣🟡)
- ✨ Actualización automática en 5 minutos (timeout)

**Ejemplo:**
![lista_de_items demo]

---

### 2️⃣ `/item`
Muestra detalles completos de un item específico.

**Uso:**
```
/item                              # Abre selector de items
/item id:1                         # Buscar por ID
/item nombre:Poción               # Buscar por nombre
/item id_o_nombre:sword_basic_001 # Buscar por key
```

**Búsqueda:**
- ✅ Por **ID** (número): `/item id:1`
- ✅ Por **nombre**: `/item nombre:Poción` (búsqueda parcial)
- ✅ Por **item_key**: `/item id_o_nombre:potion_mega_001`
- ✅ Sin parámetros: Abre selector de todos los items

**Información que Muestra:**
```
📦 Item Name                              ← Nombre con emoji de rareza
┌─────────────────────────────────────
│ Descripción del item
├─ ℹ️ Información
│  • ID: 1
│  • Key: potion_mega_001
│  • Rareza: 🟡 Legendary
│  • Origen: 🎲 Gacha / 🏪 Tienda
│
├─ ⚙️ Stats
│  ⚔️ Ataque: 5
│  🛡️ Defensa: 10
│  ❤️ Vida: 50
│  🔗 Armadura: 15
│  🔧 Mantenimiento: 3
└─────────────────────────────────────
```

---

## 🎨 Emojis de Rareza

| Emoji | Rareza | Color |
|-------|--------|-------|
| ⚪ | Common | Gris |
| 🟢 | Uncommon | Verde |
| 🔵 | Rare | Azul |
| 🟣 | Epic | Púrpura |
| 🟡 | Legendary | Oro |

---

## 📊 Estadísticas Mostradas

Al usar `/lista_de_items` verás:

```
📊 Estadísticas
• Total: 9 items
• Gacha: 8
• Tienda: 1
```

---

## 🔍 Ejemplos de Búsqueda

### Búsqueda por ID
```
Usuario: /item 1
Bot: Muestra el item con ID 1
```

### Búsqueda por Nombre (parcial)
```
Usuario: /item poción
Bot: Si solo hay una coincidencia, la muestra.
     Si hay varias, abre selector.
```

### Búsqueda por Key Exacto
```
Usuario: /item sword_dragon_001
Bot: Muestra Espada Dragón
```

### Sin parámetros (Selector)
```
Usuario: /item
Bot: Abre selector con todos los items disponibles
     Usuario elige del menú
     Se muestra el item seleccionado
```

---

## 💡 Tips Útiles

### T1: Guardar Items Favoritos
Si frecuentemente buscas el mismo item, guarda el comando:
```
/item sword_basic_001
```

### T2: Búsqueda Flexible
No necesitas nombre exacto:
- `poción` encuentra "Poción de Vida"
- `vida` encuentra "Poción de Vida"
- `potion` encuentra "Potion de Vida"

### T3: Múltiples Resultados
Si hay varias coincidencias, el bot abre un selector automáticamente.

### T4: Filtrar por Tipo
```
/lista_de_items source:gacha     # Solo gacha
/lista_de_items source:store     # Solo tienda
```

---

## ⚙️ Detalles Técnicos

### Cache
- Los items se cachean en memoria (O(1) lookup)
- Los datos se actualizan automáticamente cuando se importan nuevos items
- No hay latencia perceptible en búsquedas

### Límites
- Select menu muestra máximo 25 items (límite de Discord)
- Si hay más de 25 items, aparecen "los primeros" 25
- Se puede expandir con paginación (versión futura)

### Integración
- Comandos integrados con `items_manager.py`
- Datos sincronizados con base de datos SQLite
- Stats en tiempo real desde BD

---

## 🚀 Próximas Características (Roadmap)

- [ ] Paginación para más de 25 items
- [ ] Categorías de items (weapons, armor, potions, etc.)
- [ ] Filtro por stats mínimos
- [ ] Comparativa de dos items
- [ ] Items en inventario con cantidad
- [ ] Precios en tienda

---

## 📝 Notas

- El comando `/lista_de_items` muestra **todos** los items del catálogo
- El comando `/item` permite **búsqueda específica** de un item
- Ambos comandos tienen **timeouts de 5 minutos** para interactividad
- Los selectors se pueden usar una sola vez (design de Discord)

---

## ❓ Preguntas Frecuentes

**P: ¿Puedo buscar items que no existen?**
R: Sí, pero recibirás un mensaje de error con sugerencia.

**P: ¿Qué pasa si hay 2 items con el mismo nombre?**
R: Se abre un selector para que elijas cuál quieres ver.

**P: ¿Se pueden agregar más stats?**
R: Sí, modificando el JSON del item y la estructura de BD.

**P: ¿Puedo eliminar items?**
R: Sí, removiendo la carpeta de `assets/` y reimportando.

---

**Última actualización:** 15/02/2026
**Estado:** ✅ Producción
**Versión:** 1.0
