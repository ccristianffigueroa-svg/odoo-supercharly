from odoo import fields, models


class SuperCharlyExpirationAlert(models.Model):
    _name = "supercharly.expiration.alert"
    _description = "Alertas de Vencimiento SuperCharly"
    _order = "days_remaining asc"

    product_id = fields.Many2one(
        "product.product", string="Producto", readonly=True, ondelete="cascade"
    )
    lot_id = fields.Many2one(
        "stock.lot", string="Lote", readonly=True, ondelete="cascade"
    )
    expiration_date = fields.Datetime(string="Fecha de vencimiento", readonly=True)
    available_qty = fields.Float(string="Cantidad disponible", readonly=True)
    days_remaining = fields.Integer(string="Días restantes", readonly=True)
    status = fields.Selection(
        [
            ("expired", "Vencido"),
            ("critical", "Crítico"),
            ("warning", "Próximo a vencer"),
            ("attention", "En observación"),
            ("normal", "Normal"),
        ],
        string="Estado",
        readonly=True,
    )

    def generar_alertas(self):
        ahora = fields.Datetime.now()

        # Existencias por lote en ubicaciones internas (una sola consulta,
        # en lugar de una búsqueda de quants por cada lote).
        agrupado = self.env["stock.quant"]._read_group(
            domain=[
                ("lot_id", "!=", False),
                ("lot_id.expiration_date", "!=", False),
                ("location_id.usage", "=", "internal"),
            ],
            groupby=["lot_id"],
            aggregates=["quantity:sum", "reserved_quantity:sum"],
        )

        # Regenerar alertas
        self.search([]).unlink()

        valores_lista = []
        for lote, cantidad, reservada in agrupado:
            disponible = cantidad - reservada
            if disponible <= 0:
                continue

            dias = (lote.expiration_date.date() - ahora.date()).days

            if dias < 0:
                estado = "expired"
            elif dias <= 7:
                estado = "critical"
            elif dias <= 15:
                estado = "warning"
            elif dias <= 30:
                estado = "attention"
            else:
                estado = "normal"

            valores_lista.append({
                "product_id": lote.product_id.id,
                "lot_id": lote.id,
                "expiration_date": lote.expiration_date,
                "available_qty": disponible,
                "days_remaining": dias,
                "status": estado,
            })

        if valores_lista:
            self.create(valores_lista)

        return True
