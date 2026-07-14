"""Facade per la retrocompatibilità dopo il refactoring a micro-moduli."""

from app.controllers.trickplay_controller import TrickplayController
from app.ui.views.trickplay_view import TrickplayView, crea_schermata_trickplay
from app.ui.components.video_item_widget import VideoItemWidget

__all__ = ["TrickplayController", "VideoItemWidget", "TrickplayView", "crea_schermata_trickplay"]
