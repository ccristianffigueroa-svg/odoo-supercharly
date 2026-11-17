
/** @odoo-module **/

function moverBuscador() {
    const input =
        document.querySelector(
            '.pos-topheader input[placeholder="Buscar productos..."]'
        ) ||
        document.querySelector(
            '.rightpane input[placeholder="Buscar productos..."]'
        );

    if (!input) return;

    const buscador = input.closest('.input-group')?.parentElement;

    const catalogo = document.querySelector(
        '.rightpane > .position-relative'
    );

    const categorias = catalogo?.querySelector(
        '.product-list.category-list'
    );

    if (!buscador || !catalogo || !categorias) return;

    let fila = catalogo.querySelector('.sc-search-row');

    if (!fila) {
        fila = document.createElement('div');
        fila.className = 'sc-search-row';
        catalogo.insertBefore(fila, categorias);
    }

    if (buscador.parentElement !== fila) {
        fila.appendChild(buscador);
    }

    const botones = document.querySelectorAll(
        '.pos-topheader button'
    );

    const botonQR = [...botones].find(
        (button) => button.querySelector('[data-icon="barcode"]')
    );

    if (botonQR && botonQR.parentElement !== fila) {
        fila.appendChild(botonQR);
    }

    buscador.classList.add('sc-catalog-search');
}

function iniciarPersonalizacion() {
    if (!document.body) {
        document.addEventListener(
            'DOMContentLoaded',
            iniciarPersonalizacion,
            { once: true }
        );
        return;
    }

    moverBuscador();

    const observer = new MutationObserver(() => {
        moverBuscador();
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true,
    });
}

iniciarPersonalizacion();


import { MermaDialog } from "./merma_dialog";
import { patch } from "@web/core/utils/patch";
import { BurgerMenuDialog } from "@point_of_sale/app/components/navbar/burger_menu/burger_menu_dialog";

patch(BurgerMenuDialog.prototype, {
    abrirMerma() {
    this.dialog.add(MermaDialog, {});
    },
});

