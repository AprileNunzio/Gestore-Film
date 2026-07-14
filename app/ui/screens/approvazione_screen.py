"""Facade per la retrocompatibilità dopo il refactoring a micro-moduli."""

from app.controllers.approvazione_controller import ApprovazioneController
from app.ui.views.approvazione_view import ApprovazioneView, crea_schermata_approvazione

__all__ = ["ApprovazioneController", "ApprovazioneView", "crea_schermata_approvazione"]
