
{
    "name": "SuperCharly - Personalización del Punto de Venta",
    "version": "1.0.0",
    "category": "Point of Sale",
    "summary": "Personalización de la interfaz del Punto de Venta de SuperCharly",
    "depends": ["point_of_sale", "stock"],
    "data": [],
    "assets": {
        "point_of_sale._assets_pos": [
            "custom_supercharly_pos/static/src/css/supercharly_pos.css",
            "custom_supercharly_pos/static/src/js/supercharly_pos.js",
            "custom_supercharly_pos/static/src/xml/product_card.xml",
            "custom_supercharly_pos/static/src/xml/merma_menu.xml",
            "custom_supercharly_pos/static/src/js/merma_dialog.js",
            "custom_supercharly_pos/static/src/xml/merma_dialog.xml",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
