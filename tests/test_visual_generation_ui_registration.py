from app.ui.main_window import MainWindow
from app.ui.sidebar import Sidebar
from app.ui.visual_generation_tab import VisualGenerationTab


def test_image_generation_page_is_registered_in_navigation():
    assert "Image Generation" in Sidebar.NAV_ITEMS
    assert hasattr(MainWindow, "_build_visual_generation_page")
    assert VisualGenerationTab.__name__ == "VisualGenerationTab"
