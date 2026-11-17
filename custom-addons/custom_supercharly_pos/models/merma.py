
from odoo import api, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockMove(models.Model):
    _inherit = "stock.move"

    # ==========================================================
    # 1. VALIDAR PERMISOS
    # ==========================================================

    def _validar_permisos_merma_pos(self):

        if not (
            self.env.user.has_group("point_of_sale.group_pos_user")
            or self.env.user.has_group("stock.group_stock_user")
            or self.env.user.has_group("stock.group_stock_manager")
        ):
            raise UserError(
                _("No tienes permisos para registrar mermas.")
            )

    # ==========================================================
    # 2. OBTENER PRODUCTOS CON STOCK DISPONIBLE
    # ==========================================================


    @api.model
    def obtener_productos_merma_pos(self):
        self._validar_permisos_merma_pos()

        company = self.env.company
        source_location = company.default_stock_location_id

        if not source_location:
            raise UserError(
                _("La compañía no tiene una ubicación de stock configurada.")
            )

        Quant = self.env["stock.quant"].sudo()
        Product = self.env["product.product"].sudo()

        productos = Product.search([
            ("active", "=", True),
            ("is_storable", "=", True),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", company.id),
        ])

        precision = self.env["decimal.precision"].precision_get(
            "Product Unit"
        )

        resultado = []

        for product in productos:

            if product.company_id and product.company_id != company:
                continue

            cantidad = Quant._get_available_quantity(
                product,
                source_location,
            )

            if float_compare(
                cantidad,
                0.0,
                precision_digits=precision,
            ) <= 0:
                continue

            resultado.append({
                "id": product.id,
                "name": product.name or "",
                "display_name": product.display_name or "",
                "barcode": product.barcode or "",
                "default_code": product.default_code or "",
                "quantity": cantidad,
                "uom": product.uom_id.name or "",
                "tracking": product.tracking,
            })

        return resultado

    # ==========================================================
    # 3. OBTENER LOTES CON STOCK DISPONIBLE
    # ==========================================================

    @api.model
    def obtener_lotes_merma_pos(self, product_id):

        self._validar_permisos_merma_pos()

        company = self.env.company
        source_location = company.default_stock_location_id

        if not source_location:
            raise UserError(
                _("No existe una ubicación de stock configurada.")
            )

        product = self.env["product.product"].sudo().browse(
            int(product_id)
        ).exists()

        if not product:
            raise UserError(
                _("El producto seleccionado no existe.")
            )

        if product.company_id and product.company_id != company:
            raise UserError(
                _("El producto pertenece a otra compañía.")
            )

        if product.tracking != "lot":
            return []

        Lot = self.env["stock.lot"].sudo()
        Quant = self.env["stock.quant"].sudo()

        dominio = [
            ("product_id", "=", product.id),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", company.id),
        ]

        lotes = Lot.search(dominio)

        resultado = []

        for lote in lotes:

            cantidad = Quant._get_available_quantity(
                product,
                source_location,
                lot_id=lote,
                strict=True,
            )

            if float_compare(
                cantidad,
                0.0,
                precision_rounding=10 ** (-self.env["decimal.precision"].precision_get("Product Unit")),
            ) <= 0:
                continue

            resultado.append({
                "id": lote.id,
                "name": lote.name,
                "quantity": cantidad,
            })

        return resultado

    # ==========================================================
    # 4. REGISTRAR UNA MERMA
    # ==========================================================

    @api.model
    def crear_merma_pos(
        self,
        product_id,
        quantity,
        lot_id=False,
        reason_tag_ids=None,
    ):

        # ------------------------------------------------------
        # PERMISOS
        # ------------------------------------------------------

        self._validar_permisos_merma_pos()

        company = self.env.company

        # ------------------------------------------------------
        # UBICACIONES
        # ------------------------------------------------------

        source_location = company.default_stock_location_id
        scrap_location = company.scrap_location_id

        if not source_location:
            raise UserError(
                _("No existe una ubicación de stock configurada.")
            )

        if not scrap_location:
            raise UserError(
                _("No existe una ubicación de desechos configurada.")
            )

        if source_location.company_id != company:
            raise UserError(
                _("La ubicación de stock pertenece a otra compañía.")
            )

        if scrap_location.company_id != company:
            raise UserError(
                _("La ubicación de desechos pertenece a otra compañía.")
            )

        # ------------------------------------------------------
        # PRODUCTO
        # ------------------------------------------------------

        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            raise UserError(
                _("El producto seleccionado no es válido.")
            )

        product = self.env["product.product"].sudo().browse(
            product_id
        ).exists()

        if not product:
            raise UserError(
                _("El producto seleccionado no existe.")
            )

        if not product.is_storable:
            raise UserError(
                _("Solo puedes registrar mermas de productos almacenables.")
            )

        if product.company_id and product.company_id != company:
            raise UserError(
                _("El producto pertenece a otra compañía.")
            )

        # ------------------------------------------------------
        # CANTIDAD
        # ------------------------------------------------------

        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            raise UserError(
                _("La cantidad ingresada no es válida.")
            )

        if quantity <= 0:
            raise UserError(
                _("La cantidad debe ser mayor que cero.")
            )

        if float_compare(
            quantity,
            0.0,
            precision_rounding=10 ** (-self.env["decimal.precision"].precision_get("Product Unit")),
        ) <= 0:
            raise UserError(
                _("La cantidad ingresada no es válida.")
            )

        # ------------------------------------------------------
        # VALIDAR TRAZABILIDAD
        # ------------------------------------------------------

        if product.tracking == "serial":
            raise UserError(
                _("Los productos con seguimiento por número de serie "
                  "no están habilitados para este registro de merma.")
            )

        lot = False

        if product.tracking == "lot":

            if not lot_id:
                raise UserError(
                    _("Debes seleccionar un lote para este producto.")
                )

            try:
                lot_id = int(lot_id)
            except (TypeError, ValueError):
                raise UserError(
                    _("El lote seleccionado no es válido.")
                )

            lot = self.env["stock.lot"].sudo().browse(
                lot_id
            ).exists()

            if not lot:
                raise UserError(
                    _("El lote seleccionado no existe.")
                )

            if lot.product_id != product:
                raise UserError(
                    _("El lote seleccionado no corresponde al producto.")
                )

            if lot.company_id and lot.company_id != company:
                raise UserError(
                    _("El lote pertenece a otra compañía.")
                )

        elif lot_id:
            raise UserError(
                _("Este producto no requiere selección de lote.")
            )

        # ------------------------------------------------------
        # VALIDAR STOCK DISPONIBLE
        # ------------------------------------------------------

        Quant = self.env["stock.quant"].sudo()

        cantidad_disponible = Quant._get_available_quantity(
            product,
            source_location,
            lot_id=lot or False,
            strict=bool(lot),
        )

        if float_compare(
            quantity,
            cantidad_disponible,
            precision_rounding=10 ** (-self.env["decimal.precision"].precision_get("Product Unit")),
        ) > 0:
            raise UserError(
                _(
                    "Stock insuficiente para %(producto)s.\n"
                    "Disponible: %(disponible)s\n"
                    "Solicitado: %(solicitado)s"
                ) % {
                    "producto": product.display_name,
                    "disponible": cantidad_disponible,
                    "solicitado": quantity,
                }
            )

        # ------------------------------------------------------
        # VALIDAR MOTIVOS DE MERMA
        # ------------------------------------------------------

        reason_tag_ids = reason_tag_ids or []

        if not isinstance(reason_tag_ids, (list, tuple)):
            raise UserError(
                _("Los motivos de merma no son válidos.")
            )

        try:
            reason_tag_ids = [int(tag_id) for tag_id in reason_tag_ids]
        except (TypeError, ValueError):
            raise UserError(
                _("Los motivos de merma no son válidos.")
            )

        if len(reason_tag_ids) != len(set(reason_tag_ids)):
            raise UserError(
                _("No puedes repetir los motivos de merma.")
            )

        if reason_tag_ids:
            tags = self.env[
                "stock.scrap.reason.tag"
            ].sudo().browse(reason_tag_ids).exists()

            if len(tags) != len(reason_tag_ids):
                raise UserError(
                    _("Uno o más motivos de merma no existen.")
                )

        # ------------------------------------------------------
        # CREAR MOVIMIENTO DE DESECHO NATIVO
        # ------------------------------------------------------

        Move = self.env["stock.move"].sudo()

        valores = {
            "reference": _("Merma POS: %s") % product.display_name,
            "product_id": product.id,
            "product_uom_qty": quantity,
            "uom_id": product.uom_id.id,
            "location_id": source_location.id,
            "location_dest_id": scrap_location.id,
            "company_id": company.id,
            "origin": _("Punto de Venta"),
            "scrap_reason_tag_ids": [(6, 0, reason_tag_ids)],
        }

        move = Move.with_context(
            default_is_scrap=True
        ).create(valores)

        # ------------------------------------------------------
        # ASIGNAR LOTE
        # ------------------------------------------------------

        if lot:
            move.write({
                "lot_ids": [(6, 0, [lot.id])],
            })

        # ------------------------------------------------------
        # ESTABLECER CANTIDAD
        # ------------------------------------------------------

        move.quantity = quantity

        # ------------------------------------------------------
        # EJECUTAR DESECHO NATIVO DE ODOO
        # ------------------------------------------------------

        move.action_scrap()

        return {
            "success": True,
            "message": _(
                "Merma registrada correctamente: %s"
            ) % product.display_name,
            "move_id": move.id,
        }

    # ==========================================================
    # 5. REGISTRAR VARIAS MERMAS EN UNA OPERACIÓN
    # ==========================================================

    @api.model
    def crear_mermas_pos(self, lineas):

        self._validar_permisos_merma_pos()

        if not isinstance(lineas, list) or not lineas:
            raise UserError(
                _("Debes agregar al menos un producto.")
            )

        movimientos = []

        for linea in lineas:

            if not isinstance(linea, dict):
                raise UserError(
                    _("Una de las líneas de merma no es válida.")
                )

            product_id = linea.get("product_id")
            quantity = linea.get("quantity")
            lot_id = linea.get("lot_id") or False
            reason_tag_ids = linea.get("reason_tag_ids") or []

            resultado = self.crear_merma_pos(
                product_id,
                quantity,
                lot_id,
                reason_tag_ids,
            )

            movimientos.append(resultado["move_id"])

        return {
            "success": True,
            "message": _(
                "Se registraron correctamente %s mermas."
            ) % len(movimientos),
            "move_ids": movimientos,
            "total": len(movimientos),
        }
