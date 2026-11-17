from odoo import fields, models
from datetime import timedelta
import math


class SuperCharlyDemandForecast(models.Model):
    _name = "supercharly.demand.forecast"
    _description = "Predicción de Demanda SuperCharly"
    _order = "suggested_qty desc"

    product_id = fields.Many2one(
        "product.product", string="Producto", required=True, readonly=True,
        ondelete="cascade",
    )
    qty_sold = fields.Float(string="Unidades vendidas (30 días)", readonly=True)
    avg_daily_sales = fields.Float(
        string="Promedio diario", readonly=True, digits=(16, 2)
    )
    forecast_qty = fields.Float(
        string="Demanda estimada (7 días)", readonly=True, digits=(16, 2)
    )
    current_stock = fields.Float(string="Stock disponible", readonly=True)
    suggested_qty = fields.Float(string="Cantidad recomendada", readonly=True)
    last_updated = fields.Datetime(string="Última actualización", readonly=True)

    def generar_predicciones(self):
        fecha_fin = fields.Datetime.now()
        fecha_inicio = fecha_fin - timedelta(days=30)

        # 1. Ventas POS de los últimos 30 días, agrupadas en la base de datos
        #    (evita cargar todas las líneas en memoria).
        agrupado = self.env["pos.order.line"]._read_group(
            domain=[
                ("order_id.state", "in", ["paid", "done", "invoiced"]),
                ("order_id.date_order", ">=", fecha_inicio),
                ("order_id.date_order", "<=", fecha_fin),
                ("product_id", "!=", False),
            ],
            groupby=["product_id"],
            aggregates=["qty:sum"],
        )
        ventas = {producto.id: cantidad for producto, cantidad in agrupado}

        # 2. Productos activos y almacenables
        Producto = self.env["product.product"]
        dominio = [("active", "=", True)]
        if "is_storable" in Producto._fields:
            dominio.append(("is_storable", "=", True))
        productos = Producto.search(dominio)

        # 3. Predicciones existentes
        registros_por_producto = {
            r.product_id.id: r for r in self.search([])
        }

        ahora = fields.Datetime.now()
        nuevos = []

        # 4. Cálculo
        for producto in productos:
            cantidad_vendida = max(0.0, ventas.get(producto.id, 0.0))
            promedio_diario = cantidad_vendida / 30.0
            demanda_7_dias = promedio_diario * 7.0
            stock_disponible = producto.qty_available
            stock_seguridad = promedio_diario * 2.0

            diferencia = max(
                0.0, demanda_7_dias + stock_seguridad - stock_disponible
            )

            valores = {
                "qty_sold": cantidad_vendida,
                "avg_daily_sales": promedio_diario,
                "forecast_qty": demanda_7_dias,
                "current_stock": stock_disponible,
                "suggested_qty": float(math.ceil(diferencia)),
                "last_updated": ahora,
            }

            registro = registros_por_producto.get(producto.id)
            if registro:
                registro.write(valores)
            else:
                valores["product_id"] = producto.id
                nuevos.append(valores)

        if nuevos:
            self.create(nuevos)

        return True
