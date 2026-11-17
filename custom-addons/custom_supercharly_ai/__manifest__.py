{
    "name": "SuperCharly - Inteligencia de Inventario",
    "version": "1.0.0",
    "category": "Inventory",
    "summary": "Predicción de demanda y gestión inteligente de inventario",
    "description": """
        Sistema de inteligencia de inventario para SuperCharly.
        Incluye predicción de demanda, reposición inteligente,
        clasificación de productos, alertas de vencimiento
        y análisis de mermas.
    """,
    "depends": [
        "stock",
        "point_of_sale",
        "purchase",
        "purchase_stock",
        "product_expiry",
    ],
    "data": [
        "security/ir.access.csv",
        "views/prediccion_views.xml",
        "views/vencimiento_views.xml",
        "views/reposicion_views.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}