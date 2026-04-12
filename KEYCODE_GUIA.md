# Guía de Keycodes en PowerBot

## ✅ Implementación Completada

Se ha agregado soporte completo para **keycodes** (códigos de acceso de un solo uso) en el sistema de tienda de Discord.

---

## 📋 Estructura de un Item Keycode

Los keycodes se configuran igual que items sound, pero con una categoría especial:

```json
{
  "item_key": "keycode_1",
  "nombre": "Keycode Tier 1",
  "descripcion": "Código de acceso exclusivo. Te llegará por mensaje privado.",
  "base_price": 100,
  "quantity": 3,
  "ip%": 0.0,
  "cooldown": 0,
  "global_cooldown": 0,
  "thumbnail": "thumbnail.gif",
  "video": "video.mp4",
  "rareza": "rare",
  "metadata": {
    "categoria": "keycode",
    "peso": 0,
    "vendible": false,
    "tradeable": false,
    "stackable": false,
    "stream": false,
    "keycodes": [
      "KC-TIER1-ABC123XYZ789",
      "KC-TIER1-DEF456UVW012",
      "KC-TIER1-GHI789RST345"
    ]
  }
}
```

### Parámetros Especiales
- **metadata.categoria**: Debe ser `"keycode"`, `"key"` o `"code"`
- **metadata.keycodes**: Array de strings con los códigos disponibles
- **metadata.stream**: Si es `true`, requiere stream activo para canjearla
- **quantity**: Se sincroniza automáticamente con `len(metadata.keycodes)`
- **video**: Obligatorio (se reproducirá en notificación)
- **audio**: NO debe existir (los keycodes no tienen audio)
- **thumbnail**: Obligatorio (se mostrará en el embed)

---

## 🔐 Flujo de Compra de Keycode

1. **Usuario inicia compra** → Se valida:
   - Tienda abierta
   - Item existente y en stock
   - Stream requerido (si `metadata.stream: true`)
   - Saldo suficiente
   - No en cooldown

2. **Sistema pide confirmación** → Muestra precio con descuentos aplicables

3. **Usuario confirma** → Se ejecuta:
   - Descuento de puntos
   - Extrae primer código de `metadata.keycodes`
   - Actualiza config.json del item
   - Envía código por DM privado (formato completo)
   - Registra cooldown
   - Publica notificación en livefeed (código CENSURADO)

4. **Código se consume** → Ya no puede volver a usarse
   - Quantity disminuye en 1
   - El config.json se actualiza automáticamente
   - Cuando quantity == 0, el item aparece sin stock

---

## 📧 Mensaje Privado al Usuario

Cuando alguien compra un keycode, recibe un DM privado con:
- ✅ Nombre del item
- ✅ Código completo en bloque de código
- 🔔 Nota sobre que es de uso único y personal

**Ejemplo:**
```
🔑 Código canjeado
Has comprado Keycode Tier 1

Tu código (uso único)
KC-TIER1-ABC123XYZ789

⚠️ Importante
Este código es de uso único y personal. No lo compartas.

Guarda este código en un lugar seguro.
```

---

## 📢 Notificación en Livefeed

En el livefeed, se publica una notificación con:
- 🎥 Video del item
- 👤 Nombre de quien compró
- 🔑 Código CENSURADO (formato: `KC-TIER1-***`)

**Formato censurado:** Muestra primeros 5 caracteres + últimos 3 caracteres solamente.

```
Ejemplo visible en logs públicos:
"jugador canjeó Keycode Tier 1 (código: KC-TI...XYZ789)"

NO se expondrá nunca la parte intermedia del código.
```

---

## 🛡️ Consideraciones de Seguridad

✅ **Códigos de un solo uso**
- Una vez consumido, se elimina del array
- No puede ser compartido sin exposición pública

✅ **DM Privada Garantizada**
- El código completo SOLO llega por DM
- El log público apenas muestra pistas

✅ **Reembolsos Automáticos**
- Si falla el envío de DM, se investiga pero NO se reembolsa
- Si falla el consumo de código: reembolso automático
- Si falla el descuento: transacción rechazada

✅ **Validaciones Estrictas**
- array `metadata.keycodes` debe existir y no estar vacío
- Cada código debe ser string no vacío
- quantity debe coincidir con len(keycodes)
- Video es obligatorio, audio no existe

✅ **Stream Requerido (Opcional)**
- Si `metadata.stream: true`, solo se puede canjear con stream activo
- Evita que se compartan códigos sin estar "presentes"

---

## 🧪 Cómo Probar

### 1. Item de Prueba Ya Creado
Un item de prueba está disponible en:
```
assets/store/keycode_1/
├── config.json (3 códigos de prueba)
├── thumbnail.gif (placeholder)
└── video.mp4 (placeholder)
```

### 2. Pasos para Probar

1. **Sincroniza la tienda:**
   ```
   En Discord: /sync_store (o similar)
   ```

2. **Looking at store:**
   - Verás un nuevo item: "🔑 `ID:S1` Keycode Tier 1"
   - Muestra: "3 códigos disponibles"
   - Precio: 100 puntos

3. **Compra el item:**
   - Sistema pide confirmación
   - Presionas ✅ Confirmar
   - Se descuentan 100 puntos
   - Recibes DM con: `KC-TIER1-ABC123XYZ789`
   - Se publica notificación (censurando)

4. **Verificar consumo:**
   - Abre `assets/store/keycode_1/config.json`
   - Verás que `metadata.keycodes` tiene ahora 2 códigos
   - quantity cambió a 2
   - El primer código desapareció

---

## 📝 Logs Públicos vs Privados

### Lo que ve CUALQUIERA en el livefeed:
```
"jugador123 canjeó Keycode Tier 1 (código: KC-TI...XYZ789)"
```

### Lo que ve SOLO el usuario por DM:
```
Tu código (uso único)
KC-TIER1-ABC123XYZ789
```

### Lo que ve el SERVIDOR (logs internos):
```
[KEYCODE] Consumido: keycode_1 -> KC-TIER1-ABC123XYZ789 (usuario: 123456789)
```

---

## 🔧 Crear Nuevos Keycodes

Para crear un nuevo item keycode:

1. **Crea carpeta:**
   ```
   assets/store/mi_keycode/
   ```

2. **Agrega media:**
   - `thumbnail.gif` (imagen representativa)
   - `video.mp4` (video de notificación)

3. **Crea config.json:**
   ```json
   {
     "item_key": "mi_keycode",
     "nombre": "Mi Código Especial",
     "descripcion": "Descripción del código",
     "base_price": 50,
     "quantity": -1,
     "ip%": 0.0,
     "metadata": {
       "categoria": "keycode",
       "stream": false,
       "keycodes": [
         "MIS-CODIGO-001",
         "MIS-CODIGO-002",
         "MIS-CODIGO-003"
       ],
       "vendible": false,
       "tradeable": false,
       "stackable": false
     }
   }
   ```

4. **Sincroniza:**
   - El sistema cargará automáticamente

---

## ⚠️ Errores Comunes

| Error | Causa | Solución |
|-------|-------|----------|
| "Sin stock disponible" | `metadata.keycodes` vacío | Agregar códigos a metadata |
| "keycode en índice X es inválido" | Código es null/vacío | Verificar que todos sean strings |
| "falta video" | No existe video.mp4 | Crear archivo de video |
| "No hay códigos disponibles" | Todos consumidos | Agregar más códigos al array |
| No recibe DM | Bot sin permisos | Verificar configuración DM |

---

## 🚀 Extensiones Futuras (Opcional)

1. **Comando de admin:** `/regenerate_keycodes item_key cantidad`
   - Agregua más códigos a un item

2. **Recuperación de código:**
   - Si el DM falla, guardar código en BD
   - Comando `/recover_keycode` para recuperarlo

3. **Tracking:**
   - Log en canal Discord cada consumo
   - Dashboard de códigos vendidos

4. **Validación de código:**
   - Comando `/validate_keycode codigo`
   - Para verificar si un código es válido

---

## 📞 Soporte

Si algo no funciona:
1. Revisa los logs en Discord (`/logs`)
2. Verifica que config.json está bien formado
3. Asegúrate de tener `metadata.keycodes` como array
4. Comprueba que `quantity == len(metadata.keycodes)`

¡Listo! 🎉 El sistema de keycodes está operativo.
