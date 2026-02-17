"""
Herramienta CLI para gestión de items.
Facilita la creación de nuevos items y la importación.
"""
import sys
sys.path.insert(0, 'c:\\Users\\jhon-\\Desktop\\PowerBot')

import argparse
from backend.managers.items_manager import (
    create_item_template,
    import_all_items,
    import_gacha_items,
    import_store_items,
    get_items_stats,
    validate_item_structure,
    RARITY_LEVELS
)


def cmd_create(args):
    """Crea un template de item"""
    success = create_item_template(
        item_key=args.key,
        source=args.source,
        rareza=args.rareza
    )
    
    if success:
        print(f"\n✅ Template creado exitosamente")
        print(f"\n📝 Próximos pasos:")
        print(f"   1. Edita: assets/{args.source}{'/' + args.rareza if args.source == 'gacha' else ''}/{args.key}/item.json")
        print(f"   2. Agrega una imagen: assets/{args.source}{'/' + args.rareza if args.source == 'gacha' else ''}/{args.key}/icon.png")
        print(f"   3. Importa con: python backend/managers/items_cli.py import")


def cmd_import(args):
    """Importa items"""
    if args.source == "all":
        results = import_all_items()
    elif args.source == "gacha":
        results = import_gacha_items()
    elif args.source == "store":
        results = import_store_items()
    else:
        print(f"❌ Source inválido: {args.source}")
        return


def cmd_stats(args):
    """Muestra estadísticas"""
    stats = get_items_stats()
    
    print("\n" + "=" * 60)
    print("📊 ESTADÍSTICAS DEL CATÁLOGO DE ITEMS")
    print("=" * 60)
    print(f"\n📦 Items totales: {stats['total_items']}")
    print(f"   • Gacha: {stats['gacha_items']}")
    print(f"   • Tienda: {stats['store_items']}")
    print(f"   • En caché: {stats['cached_items']}")
    
    print("\n🌟 Distribución por rareza:")
    for rarity, count in stats['by_rarity'].items():
        if count > 0:
            bar = "█" * min(count, 50)
            print(f"   {rarity.capitalize():12} {bar} {count}")
    print()


def cmd_validate(args):
    """Valida la estructura de assets"""
    result = validate_item_structure()
    
    print("\n" + "=" * 60)
    print("🔍 VALIDACIÓN DE ESTRUCTURA")
    print("=" * 60)
    
    print(f"\n✅ Items válidos: {result['total_valid']}")
    if args.verbose:
        for item in result['valid']:
            print(f"   • {item}")
    
    if result['invalid']:
        print(f"\n❌ Items inválidos: {result['total_invalid']}")
        for item in result['invalid']:
            print(f"   • {item}")
    
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Herramienta CLI para gestión de items en PowerBot"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")
    
    # Comando: create
    create_parser = subparsers.add_parser("create", help="Crear template de item")
    create_parser.add_argument("key", help="Item key único (ej: sword_legendary_001)")
    create_parser.add_argument(
        "--source",
        choices=["gacha", "store"],
        default="gacha",
        help="Origen del item (default: gacha)"
    )
    create_parser.add_argument(
        "--rareza",
        choices=RARITY_LEVELS,
        default="common",
        help="Rareza del item (solo gacha, default: common)"
    )
    
    # Comando: import
    import_parser = subparsers.add_parser("import", help="Importar items")
    import_parser.add_argument(
        "--source",
        choices=["all", "gacha", "store"],
        default="all",
        help="Qué items importar (default: all)"
    )
    
    # Comando: stats
    stats_parser = subparsers.add_parser("stats", help="Mostrar estadísticas")
    
    # Comando: validate
    validate_parser = subparsers.add_parser("validate", help="Validar estructura")
    validate_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Mostrar detalles completos"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == "create":
        cmd_create(args)
    elif args.command == "import":
        cmd_import(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "validate":
        cmd_validate(args)


if __name__ == "__main__":
    main()
