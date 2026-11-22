"""Activity-oriented preparation feedback; technical plans belong in Diagnosis."""

from __future__ import annotations

import hashlib

from editor.source_catalog.state import request_navigation
from mathmongo.reading_space.preparation import PreparationState
from mathmongo.reading_space.preparation import ReadingPreparation
from mathmongo.reading_space.preparation import ReadingPreparationStatus


def preparation_message(status: ReadingPreparationStatus) -> str:
    """Explain an operation and its recovery without exposing database internals."""
    if status.ready:
        return 'Función preparada: puedes guardar notas y subrayados. Prepararla no publica ningún borrador.'
    if status.state == PreparationState.PENDING:
        return 'Esta biblioteca necesita una preparación inicial para guardar la posición, las notas y los subrayados.'
    if status.state == PreparationState.INCOMPATIBLE:
        if status.reason == 'duplicates':
            return 'Hay registros duplicados que requieren revisión. No se ha borrado ni fusionado ningún dato. Abre Ajustes → Diagnóstico para resolverlos antes de preparar.'
        return 'La configuración de almacenamiento requiere un procedimiento de revisión. No se sustituirán índices ni se migrarán datos desde este botón. Abre Ajustes → Diagnóstico.'
    messages = {
        'permission': 'No se pudo comprobar o completar la preparación con los permisos de esta conexión. El borrador se conserva. Revisa los permisos en Ajustes → Conexiones y vuelve a comprobar.',
        'connection': 'No se pudo comprobar o completar la preparación porque la conexión no responde. El borrador se conserva. Comprueba la conexión y reintenta.',
        'context': 'La base activa o la versión de la función cambió. No se aplicaron cambios. Vuelve a comprobar la biblioteca seleccionada.',
        'verification': 'La preparación no quedó confirmada por el servidor. El borrador se conserva; vuelve a comprobar antes de intentar guardar.',
    }
    return messages.get(status.reason, 'No se pudo comprobar la preparación. Esto no significa que falten índices. El borrador se conserva; reintenta o abre Ajustes → Diagnóstico.')


def render_reading_preparation(ui, context, *, preparation=None) -> ReadingPreparationStatus:
    """Inspect each render, apply only on an explicit action, then read back."""
    preparation = preparation or ReadingPreparation(context.database, connection_label=context.connection_label)
    status = preparation.inspect()
    scope = hashlib.sha256((status.context + status.version).encode()).hexdigest()[:20]
    key = 'reading_space_preparation_' + scope
    if status.ready:
        if ui.session_state.pop(key + '_prepared', False):
            ui.success(preparation_message(status))
        return status
    if status.state == PreparationState.PENDING:
        ui.warning(preparation_message(status))
        ui.caption(f'Sólo se crearán los índices aprobados que falten en «{context.database_name}». No se borran datos, no se sustituyen índices y no se guarda ni publica el texto escrito.')
        if ui.button('Preparar notas y subrayados', key=key + '_prepare', type='primary'):
            status = preparation.prepare(status)
            if status.ready:
                ui.success(preparation_message(status))
                ui.session_state[key + '_prepared'] = True
            else:
                ui.error(preparation_message(status))
        return status
    ui.error(preparation_message(status))
    if status.state == PreparationState.UNVERIFIED:
        if ui.button('Volver a comprobar', key=key + '_retry'):
            ui.rerun()
    if ui.button('Abrir diagnóstico', key=key + '_diagnosis'):
        request_navigation(ui.session_state, 'Diagnóstico')
        ui.rerun()
    return status
