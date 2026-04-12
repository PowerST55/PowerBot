# Resumen Técnico de Cambios - Sistema de Keycodes

## Archivos Modificados

### 1. `backend/managers/store_manager.py`

#### Cambio 1: Soporte de categoría keycode
```python
def _normalize_category(metadata: Dict[str, Any]) -> str:
    # ANTES: Solo soportaba "card" y "sound"
    # AHORA: Agregado soporte para "keycode", "key", "code"
```

**Líneas afectadas:** `_normalize_category()` (aproximadamente línea 142)

#### Cambio 2: Validación de keycodes en carga
```python
def _load_item_config(...):
    # NUEVO: Validación específica para keycodes
    # - Requiere metadata.keycodes como array no vacío
    # - Requiere video, NO requiere audio
    # - Valida que cada código sea string válido
    # - Syncroniza quantity con len(metadata.keycodes)
```

**Líneas afectadas:** `_load_item_config()` (aproximadamente línea 238-271)

#### Cambio 3: Nueva función consume_keycode
```python
def consume_keycode(item_key: str) -> Dict[str, Any]:
    """
    Nueva función que:
    - Extrae el primer código del array metadata.keycodes
    - Actualiza el config.json del item
    - Retorna: {success, keycode, remaining, message}
    - Maneja locks para evitar race conditions
    """
```

**Líneas agregadas:** Nueva función completa (aproximadamente líneas 378-498)

---

### 2. `backend/services/discord_bot/store/store_packager.py`

#### Cambio 1: Normalización de categoría keycode
```python
def _normalize_item_category(item):
    # NUEVO: Soporte para "keycode", "key", "code"
```

**Líneas afectadas:** `_normalize_item_category()` (aproximadamente línea 164)

#### Cambio 2: Nuevo embed para keycodes
```python
def _build_keycode_embed(item, currency_symbol):
    """
    NUEVO: Método que construye embed específico para keycodes
    - Emoji: 🔑
    - Muestra cantidad de códigos disponibles
    - Nota sobre uso único
    - Validación de stock
    """
```

**Líneas agregadas:** Nueva función (aproximadamente líneas 271-308)

#### Cambio 3: Ruteo en _build_embed
```python
def _build_embed(...):
    # MODIFICADO: Agregado elif para keycode
    if item_category == "keycode":
        return DiscordStorePackager._build_keycode_embed(...)
```

**Líneas afectadas:** `_build_embed()` (aproximadamente línea 455)

---

### 3. `backend/services/discord_bot/store/store_sales.py`

#### Cambio 1: Categorización de keycode
```python
def _normalize_item_category(item):
    # MODIFICADO: Agregado soporte para "keycode"
```

**Líneas afectadas:** `_normalize_item_category()` (aproximadamente línea 161)

#### Cambio 2: Embed de stream requerido para keycode
```python
def _stream_required_for_keycode_embed():
    # NUEVO: Embed específico cuando stream es requerido
```

**Líneas agregadas:** Nueva función (aproximadamente línea 183)

#### Cambio 3: Envío de código por DM
```python
async def _send_keycode_via_dm(user, keycode, item_name):
    """
    NUEVO: Envía el código por DM privado
    - Crea embed con código en bloque
    - Nota de seguridad
    - Manejo de errores
    """
```

**Líneas agregadas:** Nueva función (aproximadamente línea 192)

#### Cambio 4: Notificación con censura
```python
async def _send_keycode_purchase_notification(interaction, item, keycode):
    """
    NUEVO: Publica notificación censurando el código
    - Censura: primeros 5 + últimos 3 caracteres
    - Sin audio (diferente a sound)
    - Fuente: "discord_keycode_purchase"
    """
```

**Líneas agregadas:** Nueva función (aproximadamente línea 221)

#### Cambio 5: Lógica de compra de keycode
```python
async def _finalize_keycode_purchase(interaction, item_key):
    """
    NUEVO: Flujo completo de compra de keycode
    - Validaciones (tienda, item, stream condicional)
    - Cálculo de precio
    - Descuento de puntos
    - Consumo de código mediante consume_keycode()
    - Envío de DM
    - Reembolsos automáticos en caso de error
    - Cooldown
    - Notificación
    """
```

**Líneas agregadas:** Nueva función (aproximadamente línea 252-415)

#### Cambio 6: Modificación de StorePurchaseConfirmView
```python
class StorePurchaseConfirmView(discord.ui.View):
    def __init__(self, ..., item_category="sound", ...):
        # MODIFICADO: Agregado parámetro item_category
    
    async def confirm_purchase(self, ...):
        # MODIFICADO: Lógica para decidir entre sound y keycode
        if self.item_category == "keycode":
            embed = await _finalize_keycode_purchase(...)
        else:
            embed = await _finalize_sound_purchase(...)
```

**Líneas afectadas:** `StorePurchaseConfirmView.__init__()` y `confirm_purchase()` (aproximadamente líneas 229-273)

#### Cambio 7: Extensión de process_item_purchase
```python
async def process_item_purchase(interaction, item_key):
    """
    MODIFICADO: Ahora soporta tanto sound como keycode
    - Validación de categoría expandida
    - Lógica para validar stream condicional
    - Pasa item_category a StorePurchaseConfirmView
    """
```

**Líneas afectadas:** `process_item_purchase()` (aproximadamente línea 417-462)

---

## Lógica de Seguridad Implementada

### 1. **Censura de Códigos en Logs**
```python
# Formato: "KC-TIER1-***" (primeros 5 + últimos 3)
censored_code = f"{keycode[:5]}{'*' * max(0, len(keycode) - 8)}{keycode[-3:]}"
```

### 2. **Reembolsos en Cascada**
```
Compra fallida en cualquier punto:
1. ¿Falló descuento? → No continuar
2. ¿Falló consume_keycode()? → Reembolsar
3. ¿Falló envío DM? → Log pero no reembolsar (código ya consumido)
```

### 3. **Locks Thread-Safe**
```python
# En consume_keycode():
with _LOCK:
    # Operaciones atómicas en cache
    # Actualización de archivo sincronizadas
```

### 4. **Validación de Integridad**
```python
# Al cargar item keycode:
- Verificar metadata.keycodes es array
- Verificar cada código es string no vacío
- Verificar quantity == len(keycodes)
- Verificar requiere video, NO audio
```

---

## Flujo de Datos

```
COMPRA INITIATION
    ↓
process_item_purchase()
    ├─ Valida tienda, item, categoría
    ├─ Valida stream (si sound) o stream condicional (si keycode)
    ├─ Valida stock
    ├─ Valida perfil y saldo
    ├─ Pide confirmación (StorePurchaseConfirmView)
    ↓
confirm_purchase() [Usuario presiona ✅]
    ├─ Defer para operación larga
    ├─ Decide: sound → _finalize_sound_purchase()
    │         keycode → _finalize_keycode_purchase()
    ↓
_finalize_keycode_purchase()
    ├─ Descuenta puntos
    ├─ Llama store_manager.consume_keycode()
    │   ├─ Lee config.json
    │   ├─ Extrae primer código
    │   ├─ Actualiza metadata.keycodes (elimina primero)
    │   ├─ Actualiza quantity
    │   ├─ Guarda config.json
    │   └─ Retorna {success, keycode}
    ├─ Envía DM con código completo
    ├─ Registra cooldown
    ├─ Sincroniza post en foro
    ├─ Envía notificación (censurando)
    └─ Retorna embed de éxito
```

---

## Variables Importantes

### En store_manager.py
- `_STORE_ITEMS_BY_KEY`: Cache en memoria (actualizado por consume_keycode)
- `_LOCK`: Threading lock para operaciones atómicas

### En store_sales.py
- `item_category`: "sound", "keycode", o "card"
- `requires_stream`: Bool que controla validación de stream

---

## Compatibilidad

✅ **Backward Compatible**
- Todos los cambios son aditivos
- Items sound funcionan igual que antes
- Items card funcionan igual que antes
- Solo se agregó nueva categoría

❌ **Breaking Changes**
- Ninguno

---

## Testing Recomendado

1. ✅ Cargar item keycode existente (KC_1)
2. ✅ Ver embed correcto en tienda 🔑
3. ✅ Comprar y recibir DM con código
4. ✅ Verificar config.json si fue actualizado
5. ✅ Intentar comprar nuevo: debe haber -1 código
6. ✅ Verificar notificación con código censurado
7. ✅ Comprobar reembolso si falla envío DM
8. ✅ Test con metadata.stream: true (requiere stream)

---

## Performance

- **Overhead**: Mínimo (solo lectura/escritura de 1 archivo por compra)
- **Lock Contention**: Bajo (solo durante consume_keycode)
- **DM Performance**: Asincrónico, no bloquea compra
- **Notificación**: Asincrónica, no bloquea compra

---

Fin del resumen técnico. ✅
