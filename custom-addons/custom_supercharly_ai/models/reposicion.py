
from odoo import fields, models, _
from odoo.exceptions import UserError
from datetime import timedelta
from collections import defaultdict
import math


class SuperCharlyReplenishment(models.Model):
    _name = "supercharly.replenishment"
    _description = "Reposición Inteligente SuperCharly"
    _order = "suggested_qty desc"

    STOCK_MINIMO = 20
    DIAS_SEGURIDAD = 2

    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        readonly=True,
        ondelete="cascade",
    )

    current_stock = fields.Float(
        string="Stock disponible",
        readonly=True,
    )

    forecast_qty = fields.Float(
        string="Demanda estimada",
        readonly=True,
    )

    suggested_qty = fields.Float(
        string="Cantidad recomendada",
        readonly=True,
    )

    purchase_qty = fields.Float(
        string="Cantidad a comprar",
        default=0.0,
        help="Cantidad modificable antes de generar la solicitud.",
    )

    supplierinfo_id = fields.Many2one(
        "product.supplierinfo",
        string="Información del proveedor",
        readonly=True,
        ondelete="set null",
    )

    supplier_id = fields.Many2one(
        "res.partner",
        string="Proveedor",
        related="supplierinfo_id.partner_id",
        store=True,
        readonly=True,
    )

    supplier_min_qty = fields.Float(
        string="Mínimo del proveedor",
        readonly=True,
    )

    unit_price = fields.Float(
        string="Precio del proveedor",
        readonly=True,
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        readonly=True,
    )

    lead_time = fields.Integer(
        string="Plazo de entrega (días)",
        readonly=True,
    )

    status = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("no_supplier", "Sin proveedor"),
            ("rfq_created", "Solicitud preparada"),
            ("confirmed", "Compra confirmada"),
            ("received", "Recibido"),
            ("not_needed", "Stock suficiente"),
        ],
        string="Estado",
        default="pending",
        readonly=True,
    )

    purchase_id = fields.Many2one(
        "purchase.order",
        string="Solicitud de presupuesto",
        readonly=True,
        ondelete="set null",
    )

    last_updated = fields.Datetime(
        string="Última actualización",
        readonly=True,
    )

    # ---------------------------------------------------------
    # UTILIDADES
    # ---------------------------------------------------------

    def _nombre_campo(self, modelo, *candidatos):
        campos = self.env[modelo]._fields

        for candidato in candidatos:
            if candidato in campos:
                return candidato

        return None

    def _unidad_proveedor(self, info, producto):
        campo = self._nombre_campo(
            "product.supplierinfo",
            "product_uom_id",
            "product_uom",
            "uom_id",
        )

        unidad = info[campo] if campo else False

        return unidad or producto.uom_po_id or producto.uom_id

    def _convertir_a_unidad_producto(
        self,
        cantidad,
        unidad,
        producto,
    ):
        if not unidad or unidad == producto.uom_id:
            return cantidad

        if unidad.category_id != producto.uom_id.category_id:
            raise UserError(
                _(
                    "La unidad de compra del proveedor no es compatible "
                    "con la unidad del producto %s."
                ) % producto.display_name
            )

        return unidad._compute_quantity(
            cantidad,
            producto.uom_id,
        )

    # ---------------------------------------------------------
    # BUSCAR PROVEEDOR
    # ---------------------------------------------------------

    def _buscar_proveedor(self, producto, fecha, cantidad=0.0):
        proveedores = producto.seller_ids.filtered(
            lambda proveedor: (
                (
                    not proveedor.company_id
                    or proveedor.company_id == self.env.company
                )
                and (
                    not proveedor.date_start
                    or proveedor.date_start <= fecha
                )
                and (
                    not proveedor.date_end
                    or proveedor.date_end >= fecha
                )
                and (
                    not proveedor.product_id
                    or proveedor.product_id == producto
                )
            )
        )

        if not proveedores:
            return self.env["product.supplierinfo"]

        compatibles = []

        for proveedor in proveedores:
            unidad = self._unidad_proveedor(
                proveedor,
                producto,
            )

            minimo_producto = self._convertir_a_unidad_producto(
                proveedor.min_qty,
                unidad,
                producto,
            )

            compatibles.append((proveedor, minimo_producto))

        elegibles = [
            item for item in compatibles
            if item[1] <= cantidad
        ]

        if elegibles:
            elegibles.sort(
                key=lambda item: (
                    item[0].sequence,
                    -item[1],
                )
            )
            return elegibles[0][0]

        compatibles.sort(
            key=lambda item: (
                item[0].sequence,
                item[1],
            )
        )

        return compatibles[0][0]

    # ---------------------------------------------------------
    # CALCULAR CANTIDAD SUGERIDA
    # ---------------------------------------------------------

    def _calcular_cantidad_sugerida(
        self,
        prediccion,
        stock_actual=None,
    ):
        # Utilizar el inventario real de Odoo cuando esté disponible.
        if stock_actual is None:
            stock_actual = prediccion.current_stock

        stock_actual = max(stock_actual, 0.0)
        demanda_7_dias = max(prediccion.forecast_qty, 0.0)
        promedio_diario = max(prediccion.avg_daily_sales, 0.0)

        stock_seguridad = (
            promedio_diario * self.DIAS_SEGURIDAD
        )

        # Si alcanza el stock mínimo, no se necesita reponer.
        if stock_actual >= self.STOCK_MINIMO:
            return 0.0

        stock_objetivo = max(
            self.STOCK_MINIMO,
            demanda_7_dias + stock_seguridad,
        )

        cantidad = max(
            0.0,
            stock_objetivo - stock_actual,
        )

        return float(math.ceil(cantidad))

    # ---------------------------------------------------------
    # SINCRONIZAR REPOSICIONES CON COMPRAS
    # ---------------------------------------------------------

    def _sincronizar_compras(self):
        """
        Compra cancelada:
            Desvincula la compra y devuelve a pendiente.

        Compra confirmada:
            Corrige el estado a confirmed.

        Recepción completa:
            Elimina la reposición finalizada.
        """

        registros = self.sudo().search([
            ("purchase_id", "!=", False),
        ])

        for registro in registros:
            orden = registro.purchase_id

            if not orden.exists():
                registro.write({
                    "purchase_id": False,
                    "status": "pending",
                })
                continue

            if orden.state == "cancel":
                registro.write({
                    "purchase_id": False,
                    "status": "pending",
                })
                continue

            if orden.receipt_status == "full":
                registro.unlink()
                continue

            if orden.state in ("purchase", "done"):
                if registro.status != "confirmed":
                    registro.write({
                        "status": "confirmed",
                    })
                continue

            if orden.state in ("draft", "sent", "to approve"):
                if registro.status != "rfq_created":
                    registro.write({
                        "status": "rfq_created",
                    })

    # ---------------------------------------------------------
    # ACTUALIZAR REPOSICIÓN
    # ---------------------------------------------------------

    def actualizar_reposicion(self):
        Forecast = self.env["supercharly.demand.forecast"]

        # Sincronizar primero las compras.
        self._sincronizar_compras()

        # Mantener las compras que siguen activas.
        en_curso = self.search([
            ("purchase_id", "!=", False),
            ("status", "in", ("rfq_created", "confirmed")),
        ])

        productos_en_curso = set(en_curso.product_id.ids)

        # Eliminar recomendaciones anteriores sin compra.
        recomendaciones_antiguas = self.search([
            ("purchase_id", "=", False),
        ])

        if recomendaciones_antiguas:
            recomendaciones_antiguas.unlink()

        dominio = [
            ("product_id.purchase_ok", "=", True),
        ]

        if productos_en_curso:
            dominio.append((
                "product_id",
                "not in",
                list(productos_en_curso),
            ))

        predicciones = Forecast.search(dominio)

        fecha = fields.Date.context_today(self)
        ahora = fields.Datetime.now()

        lista_valores = []

        for prediccion in predicciones:
            producto = prediccion.product_id

            # IMPORTANTE:
            # Consultar el stock real de Odoo.
            # No utilizar prediccion.current_stock para esta operación.
            stock_actual = producto.with_company(
                self.env.company
            ).qty_available

            # Calcular la reposición con el stock actualizado.
            cantidad = self._calcular_cantidad_sugerida(
                prediccion,
                stock_actual,
            )

            proveedor = self._buscar_proveedor(
                producto,
                fecha,
                cantidad,
            )

            valores = {
                "product_id": producto.id,
                "current_stock": stock_actual,
                "forecast_qty": prediccion.forecast_qty,
                "suggested_qty": cantidad,
                "purchase_qty": cantidad,
                "last_updated": ahora,
            }

            if proveedor:
                unidad_proveedor = self._unidad_proveedor(
                    proveedor,
                    producto,
                )

                valores.update({
                    "supplierinfo_id": proveedor.id,
                    "supplier_min_qty": proveedor.min_qty,
                    "unit_price": proveedor.price,
                    "currency_id": proveedor.currency_id.id,
                    "lead_time": proveedor.delay,
                })

                minimo_producto = self._convertir_a_unidad_producto(
                    proveedor.min_qty,
                    unidad_proveedor,
                    producto,
                )

                # Aplicar mínimo del proveedor solamente
                # cuando realmente se necesita reponer.
                if cantidad > 0 and minimo_producto > 0:
                    valores["purchase_qty"] = max(
                        cantidad,
                        math.ceil(minimo_producto),
                    )

            if cantidad <= 0:
                valores["status"] = "not_needed"
            elif proveedor:
                valores["status"] = "pending"
            else:
                valores["status"] = "no_supplier"

            lista_valores.append(valores)

        if lista_valores:
            self.create(lista_valores)

        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    # ---------------------------------------------------------
    # GENERAR SOLICITUDES DE COMPRA
    # ---------------------------------------------------------

    def generar_solicitud(self):
        seleccionados = self.filtered(
            lambda registro: (
                not registro.purchase_id
                and registro.status in (
                    "pending",
                    "no_supplier",
                    "not_needed",
                )
                and registro.purchase_qty > 0
            )
        )

        if not seleccionados:
            raise UserError(
                _(
                    "Selecciona uno o varios productos con "
                    "cantidad a comprar mayor que cero."
                )
            )

        sin_proveedor = seleccionados.filtered(
            lambda registro: not registro.supplierinfo_id
        )

        if sin_proveedor:
            nombres = ", ".join(
                sin_proveedor.mapped("product_id.display_name")
            )

            raise UserError(
                _(
                    "Estos productos no tienen proveedor configurado: %s"
                ) % nombres
            )

        grupos = defaultdict(lambda: self.browse())

        for registro in seleccionados:
            grupos[registro.supplier_id.id] |= registro

        Purchase = self.env["purchase.order"]
        PurchaseLine = self.env["purchase.order.line"]

        campo_uom_linea = self._nombre_campo(
            "purchase.order.line",
            "product_uom_id",
            "product_uom",
        )

        ordenes_creadas = Purchase.browse()
        hoy = fields.Date.context_today(self)

        for proveedor_id, registros in grupos.items():
            orden = Purchase.create({
                "partner_id": proveedor_id,
                "company_id": self.env.company.id,
                "date_order": fields.Datetime.now(),
            })

            ordenes_creadas |= orden

            for registro in registros:
                producto = registro.product_id
                info = registro.supplierinfo_id

                unidad = self._unidad_proveedor(
                    info,
                    producto,
                )

                cantidad_compra = producto.uom_id._compute_quantity(
                    registro.purchase_qty,
                    unidad,
                )

                fecha_entrega = (
                    fields.Datetime.now()
                    + timedelta(days=info.delay or 0)
                )

                precio = info.price

                if info.currency_id and orden.currency_id:
                    precio = info.currency_id._convert(
                        precio,
                        orden.currency_id,
                        orden.company_id,
                        hoy,
                    )

                valores_linea = {
                    "order_id": orden.id,
                    "product_id": producto.id,
                    "name": producto.display_name,
                    "product_qty": cantidad_compra,
                    "date_planned": fecha_entrega,
                    "price_unit": precio,
                }

                if campo_uom_linea:
                    valores_linea[campo_uom_linea] = unidad.id

                PurchaseLine.create(valores_linea)

                registro.write({
                    "purchase_id": orden.id,
                    "status": "rfq_created",
                })

        return {
            "type": "ir.actions.act_window",
            "name": _("Solicitudes de presupuesto"),
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [
                ("id", "in", ordenes_creadas.ids),
            ],
        }


# =============================================================
# HERENCIA DE COMPRAS
# =============================================================

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _sincronizar_reposiciones(self):
        Replenishment = self.env[
            "supercharly.replenishment"
        ].sudo()

        if not self:
            return

        # Órdenes canceladas.
        canceladas = self.filtered(
            lambda orden: orden.state == "cancel"
        )

        if canceladas:
            reposiciones = Replenishment.search([
                ("purchase_id", "in", canceladas.ids),
            ])

            if reposiciones:
                reposiciones.write({
                    "purchase_id": False,
                    "status": "pending",
                })

        # Órdenes confirmadas con recepción pendiente.
        confirmadas = self.filtered(
            lambda orden: (
                orden.state in ("purchase", "done")
                and orden.receipt_status != "full"
            )
        )

        if confirmadas:
            reposiciones = Replenishment.search([
                ("purchase_id", "in", confirmadas.ids),
                ("status", "!=", "confirmed"),
            ])

            if reposiciones:
                reposiciones.write({
                    "status": "confirmed",
                })

        # Recepciones completas.
        completas = self.filtered(
            lambda orden: orden.receipt_status == "full"
        )

        if completas:
            reposiciones = Replenishment.search([
                ("purchase_id", "in", completas.ids),
            ])

            if reposiciones:
                reposiciones.unlink()

    def button_confirm(self):
        resultado = super().button_confirm()
        self._sincronizar_reposiciones()
        return resultado

    def button_cancel(self):
        resultado = super().button_cancel()
        self._sincronizar_reposiciones()
        return resultado

    def write(self, vals):
        resultado = super().write(vals)

        if "state" in vals or "receipt_status" in vals:
            self._sincronizar_reposiciones()

        return resultado


# =============================================================
# HERENCIA DE RECEPCIONES
# =============================================================

class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        resultado = super()._action_done()

        ordenes = self.env["purchase.order"]

        for picking in self:
            if picking.picking_type_code != "incoming":
                continue

            ordenes |= (
                picking.move_ids
                .purchase_line_id
                .order_id
            )

        if ordenes:
            ordenes._sincronizar_reposiciones()

        return resultado
