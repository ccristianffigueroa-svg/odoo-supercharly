
/** @odoo-module **/

import { Component, onWillStart, signal } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

export class MermaDialog extends Component {
    static template = "custom_supercharly_pos.MermaDialog";
    static components = { Dialog };

    productos = signal([]);
    productoId = signal("");
    cantidad = signal(1);

    lotId = signal("");
    lotes = signal([]);

    lineas = signal([]);
    buscar = signal("");

    cargando = signal(true);
    guardando = signal(false);

    error = signal("");
    mensaje = signal("");

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        onWillStart(async () => {
            try {
                const productos = await this.orm.call(
                    "stock.move",
                    "obtener_productos_merma_pos",
                    []
                );

                this.productos.set(productos);

            } catch (error) {
                console.error(
                    "Error al cargar productos:",
                    error
                );

                this.error.set(
                    "No se pudieron cargar los productos."
                );

            } finally {
                this.cargando.set(false);
            }
        });
    }

    // ==========================================================
    // 1. PRODUCTO SELECCIONADO
    // ==========================================================

    get productoSeleccionado() {
        return this.productos().find(
            (producto) =>
                String(producto.id) === String(this.productoId())
        );
    }

    // ==========================================================
    // 2. FILTRAR PRODUCTOS
    // ==========================================================

    get productosFiltrados() {
        const normalizar = (valor) => {
            return String(valor || "")
                .normalize("NFD")
                .replace(/[\u0300-\u036f]/g, "")
                .trim()
                .toLowerCase();
        };

        const termino = normalizar(this.buscar());

        if (!termino) {
            return this.productos();
        }

        return this.productos().filter((producto) => {
            const nombre = normalizar(producto.name);
            const nombreCompleto = normalizar(producto.display_name);
            const codigoBarras = normalizar(producto.barcode);
            const referencia = normalizar(producto.default_code);

            return (
                nombre.includes(termino) ||
                nombreCompleto.includes(termino) ||
                codigoBarras.includes(termino) ||
                referencia.includes(termino)
            );
        });
    }


    // ==========================================================
    // 3. TOTAL DE UNIDADES
    // ==========================================================

    get totalUnidades() {
        return this.lineas().reduce(
            (total, linea) =>
                total + Number(linea.quantity),
            0
        );
    }

    // ==========================================================
    // 4. ACTUALIZAR CANTIDAD
    // ==========================================================

    actualizarCantidad(ev) {
        const valor = parseFloat(ev.target.value);

        this.cantidad.set(
            Number.isFinite(valor) ? valor : 0
        );
    }

    // ==========================================================
    // 5. SELECCIONAR PRODUCTO Y CARGAR LOTES
    // ==========================================================

    async seleccionarProducto(ev) {
        const id = ev.target.value;

        this.productoId.set(id);
        this.cantidad.set(1);

        this.lotId.set("");
        this.lotes.set([]);

        this.error.set("");

        if (!id) {
            return;
        }

        const producto = this.productoSeleccionado;

        if (producto?.tracking === "lot") {
            try {
                const lotes = await this.orm.call(
                    "stock.move",
                    "obtener_lotes_merma_pos",
                    [Number(id)]
                );

                this.lotes.set(lotes);

                if (!lotes.length) {
                    this.error.set(
                        "Este producto no tiene lotes con stock disponible."
                    );
                }

            } catch (error) {
                console.error(
                    "Error al cargar lotes:",
                    error
                );

                this.error.set(
                    error.data?.message ||
                    error.message ||
                    "No se pudieron cargar los lotes."
                );
            }
        }
    }

    // ==========================================================
    // 6. AGREGAR PRODUCTO A LA LISTA
    // ==========================================================

    agregarProducto() {
        const producto = this.productoSeleccionado;

        if (!producto) {
            this.error.set(
                "Selecciona un producto."
            );
            return;
        }

        const cantidad = Number(this.cantidad());

        if (
            !Number.isFinite(cantidad) ||
            cantidad <= 0
        ) {
            this.error.set(
                "Ingresa una cantidad válida."
            );
            return;
        }

        if (cantidad > producto.quantity) {
            this.error.set(
                "La cantidad supera el stock disponible."
            );
            return;
        }

        let lote = false;
        let stockDisponible = producto.quantity;

        if (producto.tracking === "lot") {
            if (!this.lotId()) {
                this.error.set(
                    "Debes seleccionar un lote."
                );
                return;
            }

            lote = this.lotes().find(
                (item) =>
                    String(item.id) === String(this.lotId())
            );

            if (!lote) {
                this.error.set(
                    "El lote seleccionado no es válido."
                );
                return;
            }

            stockDisponible = Number(lote.quantity);

            if (cantidad > stockDisponible) {
                this.error.set(
                    "La cantidad supera el stock disponible del lote."
                );
                return;
            }
        }

        // Comprobar cantidades ya agregadas
        // del mismo producto y del mismo lote.

        const cantidadExistente = this.lineas()
            .filter((linea) =>
                linea.product_id === producto.id &&
                String(linea.lot_id || "") ===
                String(lote ? lote.id : "")
            )
            .reduce(
                (total, linea) =>
                    total + Number(linea.quantity),
                0
            );

        if (
            cantidadExistente + cantidad >
            stockDisponible
        ) {
            this.error.set(
                "La cantidad total supera el stock disponible."
            );
            return;
        }

        const nuevaLinea = {
            key: `${producto.id}-${lote ? lote.id : "sin-lote"}-${Date.now()}`,

            product_id: producto.id,
            name: producto.name,

            barcode: producto.barcode || "",
            default_code: producto.default_code || "",

            quantity: cantidad,
            uom: producto.uom,

            lot_id: lote ? lote.id : false,
            lot_name: lote ? lote.name : "",

            tracking: producto.tracking,
            stock: stockDisponible,
        };

        this.lineas.set([
            ...this.lineas(),
            nuevaLinea,
        ]);

        // Limpiar selector.

        this.productoId.set("");
        this.cantidad.set(1);

        this.lotId.set("");
        this.lotes.set([]);

        this.error.set("");
        this.mensaje.set("");
    }

    // ==========================================================
    // 7. ELIMINAR PRODUCTO DE LA LISTA
    // ==========================================================

    eliminarLinea(key) {
        this.lineas.set(
            this.lineas().filter(
                (linea) => linea.key !== key
            )
        );

        this.error.set("");
    }

    // ==========================================================
    // 8. CERRAR VENTANA DE MERMAS
    // ==========================================================

    cerrarDialogo() {
        if (this.guardando()) {
            return;
        }

        this.dialog.closeAll();
    }

    // ==========================================================
    // 9. REGISTRAR TODAS LAS MERMAS
    // ==========================================================

    async registrarMerma() {
        if (!this.lineas().length) {
            this.error.set(
                "Agrega al menos un producto a la lista."
            );
            return;
        }

        this.guardando.set(true);
        this.error.set("");

        try {
            const lineas = this.lineas().map(
                (linea) => ({
                    product_id: linea.product_id,
                    quantity: linea.quantity,
                    lot_id: linea.lot_id || false,
                    reason_tag_ids: [],
                })
            );

            const resultado = await this.orm.call(
                "stock.move",
                "crear_mermas_pos",
                [lineas]
            );

            this.notification.add(
                resultado.message ||
                "Las mermas se registraron correctamente.",
                {
                    type: "success",
                }
            );

            this.dialog.closeAll();

        } catch (error) {
            console.error(
                "Error al registrar las mermas:",
                error
            );

            this.error.set(
                error.data?.message ||
                error.message ||
                "No se pudieron registrar las mermas."
            );

        } finally {
            this.guardando.set(false);
        }
    }
}
