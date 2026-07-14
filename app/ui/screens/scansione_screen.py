"""Facade per la retrocompatibilità dopo il refactoring a micro-moduli."""

from app.controllers.scansione_controller import ScansioneController, CanaleStats
from app.ui.views.scansione_view import ScansioneView, crea_schermata_scansione

__all__ = ["ScansioneController", "CanaleStats", "ScansioneView", "crea_schermata_scansione"]
