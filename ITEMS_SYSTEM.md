# 📦 Sistema de Items - PowerBot

Sistema completo de gestión de items con importación automática desde assets JSON + imágenes.

## 🏗️ Estructura de Carpetas

```
PowerBot/
├── assets/
│   ├── gacha/                    ⭐ Items de gacha
│   │   ├── common/               📦 Rareza común
│   │   │   ├── sword_basic_001/
│   │   │   │   ├── item.json
│   │   │   │   └── icon.png
│   │   │   └── shield_oak_001/
│   │   │       ├── item.json
│   │   │       └── icon.png
│   │   ├── uncommon/             📦 Rareza poco común
│   │   ├── rare/                 📦 Rareza rara
│   │   │   └── armor_steel_001/
│   │   │       ├── item.json
│   │   │       └── icon.png
│   │   ├── epic/                 📦 Rareza épica
│   │   └── legendary/            📦 Rareza legendaria
│   │       └── sword_dragon_001/
│   │           ├── item.json
│   │           └── icon.png
│   └── store/                    🏪 Items de tienda
│       └── potion_mega_001/
│           ├── item.json
│           └── icon.png
├── media/
│   └── items/                    📁 Imágenes procesadas (copias automáticas)
└── backend/
    └── managers/
        ├── items_manager.py      ⭐ Gestor de catálogo
        ├── inventory_manager.py  🎒 Gestor de inventarios de usuarios
        └── items_cli.py          🛠️ Herramienta CLI
```

## 📋 Formato del JSON (item.json)

```json
{
  "item_key": "sword_basic_001",
  "nombre": "Espada Básica",
  "descripcion": "Una espada de hierro forjada para principiantes",
  "rareza": "common",
  "stats": {
    "ataque": 10,
    "defensa": 2,
    "vida": 0,
    "armadura": 0,
    "mantenimiento": 5
  },
  "metadata": {
    "categoria": "weapon",
    "tipo": "sword",
    "peso": 5,
    "precio_tienda": 100,
    "vendible": true,
    "tradeable": true,
    "stackable": false
  }
}
```

### Campos Obligatorios
- ✅ `item_key` - Identificador único (ej: "sword_basic_001")
- ✅ `nombre` - Nombre del item
- ✅ `descripcion` - Descripción detallada
- ✅ `rareza` - Nivel de rareza

### Campos Opcionales
- `stats` - Atributos del item (default: 0)
- `metadata` - Información adicional (JSON)

## 🌟 Niveles de Rareza

1. **common** - Común ⚪
2. **uncommon** - Poco común 🟢
3. **rare** - Raro 🔵
4. **epic** - Épico 🟣
5. **legendary** - Legendario 🟠

## 🛠️ Herramienta CLI

### Crear nuevo item
```bash
# Item de gacha
python backend/managers/items_cli.py create <item_key> --source gacha --rareza <rareza>

# Ejemplos
python backend/managers/items_cli.py create sword_iron_001 --source gacha --rareza common
python backend/managers/items_cli.py create armor_diamond_001 --source gacha --rareza legendary

# Item de tienda
python backend/managers/items_cli.py create potion_health_001 --source store
```

### Importar items
```bash
# Importar todos
python backend/managers/items_cli.py import

# Importar solo gacha
python backend/managers/items_cli.py import --source gacha

# Importar solo tienda
python backend/managers/items_cli.py import --source store
```

### Ver estadísticas
```bash
python backend/managers/items_cli.py stats
```

### Validar estructura
```bash
# Vista resumida
python backend/managers/items_cli.py validate

# Vista detallada
python backend/managers/items_cli.py validate -v
```

## 💻 Uso Programático

### Importar desde código

```python
from backend.managers import items_manager

# Importar todos los items
results = items_manager.import_all_items()
print(f"Importados: {results['total_successful']} items")

# Importar solo gacha
gacha_results = items_manager.import_gacha_items()

# Importar solo tienda
store_results = items_manager.import_store_items()
```

### Consultar items

```python
from backend.managers import items_manager

# Por ID
item = items_manager.get_item_by_id(1)
print(f"{item['nombre']}: ATK={item['ataque']} DEF={item['defensa']}")

# Por key único
item = items_manager.get_item_by_key("sword_basic_001")

# Todos los items
all_items = items_manager.get_all_items()

# Solo items de gacha
gacha_items = items_manager.get_gacha_items()

# Solo items de tienda
store_items = items_manager.get_store_items()

# Por rareza
legendary_items = items_manager.get_items_by_rareza("legendary")

# Ruta de imagen
image_path = items_manager.get_item_image_path(item_id=1)
# Returns: Path('C:/Users/.../PowerBot/media/items/sword_basic_001.png')
```

### Estadísticas

```python
from backend.managers import items_manager

stats = items_manager.get_items_stats()
print(f"Total: {stats['total_items']}")
print(f"Gacha: {stats['gacha_items']}")
print(f"Tienda: {stats['store_items']}")
print(f"Por rareza: {stats['by_rarity']}")
```

## 🎯 Características Principales

### ✅ Sistema de Caché
- Caché en memoria para consultas ultrarrápidas
- Actualización automática al importar
- Consultas por ID o key son O(1)

### ✅ IDs Únicos
- IDs autoincrementales en base de datos
- Item keys únicos a nivel de aplicación
- Prevención de duplicados

### ✅ Múltiples Fuentes
- `source="gacha"` - Items obtenibles por gacha
- `source="store"` - Items comprables en tienda
- Filtrado automático por fuente

### ✅ Escalable
- Estructura modular por carpetas
- Fácil agregar nuevas rarezas
- Sistema de metadata extensible

### ✅ Validación
- Campos obligatorios verificados
- Estructura de carpetas validable
- Reportes de items inválidos

### ✅ Gestión de Imágenes
- Soporte múltiples formatos (PNG, JPG, WEBP, GIF)
- Copia automática a media/
- Nombres seguros (sin espacios)

## 🔄 Flujo de Trabajo

### 1. Crear nuevo item
```bash
python backend/managers/items_cli.py create legendary_sword_001 --source gacha --rareza legendary
```

### 2. Editar JSON
Edita: `assets/gacha/legendary/legendary_sword_001/item.json`

```json
{
  "item_key": "legendary_sword_001",
  "nombre": "Espada del Dragón",
  "descripcion": "Forjada con escamas de dragón milenario",
  "rareza": "legendary",
  "stats": {
    "ataque": 100,
    "defensa": 20,
    "vida": 50,
    "armadura": 10,
    "mantenimiento": 50
  },
  "metadata": {
    "categoria": "weapon",
    "tipo": "sword",
    "peso": 15,
    "vendible": false,
    "tradeable": true,
    "stackable": false,
    "efecto_especial": "fuego"
  }
}
```

### 3. Agregar imagen
Coloca `icon.png` en la misma carpeta

### 4. Importar
```bash
python backend/managers/items_cli.py import
```

### 5. Usar en código
```python
from backend.managers import items_manager

# Obtener el item
item = items_manager.get_item_by_key("legendary_sword_001")
print(f"Item creado: {item['nombre']} (ID: {item['item_id']})")
```

## 📊 Base de Datos

### Tabla: `items`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| item_id | INTEGER PK | ID único autoincremental |
| item_key | TEXT UNIQUE | Key único del item |
| source | TEXT | "gacha" o "store" |
| nombre | TEXT | Nombre del item |
| descripcion | TEXT | Descripción |
| rareza | TEXT | Nivel de rareza |
| imagen_local | TEXT | Ruta relativa de imagen |
| ataque | INTEGER | Stat de ataque |
| defensa | INTEGER | Stat de defensa |
| vida | INTEGER | Stat de vida |
| armadura | INTEGER | Stat de armadura |
| mantenimiento | INTEGER | Stat de mantenimiento |
| metadata | TEXT | JSON con data adicional |
| created_at | DATETIME | Fecha de creación |
| updated_at | DATETIME | Última actualización |

**Índices:**
- `idx_items_source` - Búsqueda por fuente
- `idx_items_rareza` - Búsqueda por rareza
- `idx_items_key` - Búsqueda por key

## 🔗 Integración con Otros Sistemas

### Inventory Manager
```python
from backend.managers import items_manager, inventory_manager

# Obtener item del catálogo
item = items_manager.get_item_by_key("sword_basic_001")

# Darlo a un usuario
inventory_manager.add_item_to_user(
    user_id=42,
    item_id=item["item_id"],
    quantity=1
)
```

### Gacha Manager (futuro)
```python
from backend.managers import items_manager, gacha_manager

# Obtener pool de items por rareza
common_items = items_manager.get_items_by_rareza("common", source="gacha")
legendary_items = items_manager.get_items_by_rareza("legendary", source="gacha")

# Configurar drop rates
gacha_manager.configure_pool(
    common_items=common_items,
    legendary_items=legendary_items
)
```

## 🧪 Testing

```bash
# Test completo del sistema
python test/test_items_manager.py
```

## 📝 Notas Importantes

1. **Item Keys Únicos**: Cada item debe tener un `item_key` único global
2. **Rareza en Carpetas**: Los items de gacha se organizan por carpetas de rareza
3. **Imágenes Opcionales**: Los items pueden no tener imagen (mostrar placeholder)
4. **Metadata Extensible**: Puedes agregar cualquier campo custom en metadata
5. **Caché Automático**: No necesitas refrescar manualmente, se actualiza en importación

## 🚀 Próximas Funciones

- [ ] Sistema de crafteo (combinar items)
- [ ] Trading entre usuarios
- [ ] Equipamiento de items
- [ ] Efectos especiales
- [ ] Durabilidad y reparación
- [ ] Sets de items con bonos
