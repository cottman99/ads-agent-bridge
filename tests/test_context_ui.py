from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace


ADDON_DIR = (
    Path(__file__).parents[1]
    / "src"
    / "ads_agent_bridge"
    / "addon"
    / "AdsAgentBridge"
)


class Signal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback

    def emit(self):
        assert self.callback is not None
        return self.callback()


class Action:
    def __init__(self, text, callback=None, icon=None):
        del icon
        self._text = text
        self._menu = None
        self._object_name = ""
        self.triggered = Signal()
        if callback is not None:
            self.callback = callback

    def text(self):
        return self._text

    def menu(self):
        return self._menu

    def setObjectName(self, value):
        self._object_name = value

    def objectName(self):
        return self._object_name


class Menu:
    def __init__(self, title=""):
        self._title = title
        self._object_name = ""
        self._actions = []

    def title(self):
        return self._title

    def setObjectName(self, value):
        self._object_name = value

    def objectName(self):
        return self._object_name

    def actions(self):
        return list(self._actions)

    def addAction(self, text):
        action = Action(text)
        self._actions.append(action)
        return action

    def addMenu(self, title):
        menu = Menu(title)
        action = Action(title)
        action._menu = menu
        menu._menu_action = action
        self._actions.append(action)
        return menu

    def menuAction(self):
        return self._menu_action

    def removeAction(self, action):
        if action in self._actions:
            self._actions.remove(action)

    # DE native menu compatibility.
    def add_action(self, action):
        self._actions.append(action)

    def remove_action(self, action):
        self.removeAction(action)

    def find_action(self, text):
        return next((action for action in self._actions if action.text() == text), None)


class MainWindow:
    def __init__(self):
        self.menubar = Menu()

    def menuBar(self):
        return self.menubar


class Clipboard:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


def _load_modules(monkeypatch):
    clipboard = Clipboard()
    qtwidgets = SimpleNamespace(
        QApplication=SimpleNamespace(instance=lambda: SimpleNamespace(clipboard=lambda: clipboard))
    )
    pyside = types.ModuleType("PySide6")
    pyside.QtWidgets = qtwidgets
    monkeypatch.setitem(sys.modules, "PySide6", pyside)

    context_spec = importlib.util.spec_from_file_location("context_ui_test_context", ADDON_DIR / "context.py")
    context_module = importlib.util.module_from_spec(context_spec)
    assert context_spec.loader is not None
    context_spec.loader.exec_module(context_module)

    ui_spec = importlib.util.spec_from_file_location("context_ui_under_test", ADDON_DIR / "context_ui.py")
    ui_module = importlib.util.module_from_spec(ui_spec)
    assert ui_spec.loader is not None
    ui_spec.loader.exec_module(ui_module)
    return context_module, ui_module, clipboard


def _keysight_modules(monkeypatch, de=None, de_app=None, dds=None, dds_app=None):
    keysight = types.ModuleType("keysight")
    ads = types.ModuleType("keysight.ads")
    keysight.ads = ads
    monkeypatch.setitem(sys.modules, "keysight", keysight)
    monkeypatch.setitem(sys.modules, "keysight.ads", ads)
    if de is not None:
        ads.de = de
        monkeypatch.setitem(sys.modules, "keysight.ads.de", de)
        de.app = de_app
        monkeypatch.setitem(sys.modules, "keysight.ads.de.app", de_app)
    if dds is not None:
        ads.dds = dds
        monkeypatch.setitem(sys.modules, "keysight.ads.dds", dds)
        dds.app = dds_app
        monkeypatch.setitem(sys.modules, "keysight.ads.dds.app", dds_app)


def test_de_registers_and_removes_callbacks_and_captures_exact_tree_selection(monkeypatch):
    context, context_ui, clipboard = _load_modules(monkeypatch)
    application = SimpleNamespace(
        popup={},
        main_popup={},
        add_popup_callback=lambda callback, name: application.popup.__setitem__(name, callback),
        add_main_popup_callback=lambda callback, name: application.main_popup.__setitem__(name, callback),
        remove_popup_callback=lambda name: application.popup.pop(name, None),
        remove_main_popup_callback=lambda name: application.main_popup.pop(name, None),
    )
    selected = SimpleNamespace(
        full_path_name="C:/demo_wrk/data/out.ds",
        name="out.ds",
        item_type=SimpleNamespace(name="DS"),
        is_workspace=False,
        is_folder=False,
        is_library=False,
        is_cell=False,
        is_view=False,
        lib_name="",
        cell_name="",
        view_name="",
    )
    de = types.ModuleType("keysight.ads.de")
    de.workspace_is_open = lambda: True
    de.active_workspace = lambda: SimpleNamespace(path="C:/demo_wrk")
    de_app = types.ModuleType("keysight.ads.de.app")
    de_app.Application = lambda: application
    de_app.WindowType = SimpleNamespace(SCHEMATIC_WINDOW=1, LAYOUT_WINDOW=2, SYMBOL_WINDOW=3)
    de_app.Action = Action
    de_app.Menu = Menu
    de_app.experimental = SimpleNamespace(selected_workspace_items=lambda: [selected])
    de_app.get_design_in_uu_from_window = lambda window: window.design
    _keysight_modules(monkeypatch, de=de, de_app=de_app)

    registry = context.ContextRegistry("de", slot="unit")
    ui = context_ui.ContextUi("de", registry)
    ui.setup()

    assert context_ui.DE_POPUP_CALLBACK in application.popup
    assert context_ui.DE_MAIN_POPUP_CALLBACK in application.main_popup
    popup = Menu()
    application.main_popup[context_ui.DE_MAIN_POPUP_CALLBACK](popup, object())
    popup.find_action(context_ui.ACTION_NAME).triggered.emit()
    captured = registry.list()[0]
    assert captured["target"]["kind"] == "dataset-ref"
    assert captured["target"]["identity"]["workspace_path"] == "C:/demo_wrk"
    assert clipboard.text.startswith("EDA_CONTEXT:v1:")

    ui.stop()
    assert application.popup == {}
    assert application.main_popup == {}


def test_dds_popup_accepts_empty_selection_and_unregisters_returned_handles(monkeypatch):
    context, context_ui, clipboard = _load_modules(monkeypatch)
    registered = {}
    unregistered = []
    dds = types.ModuleType("keysight.ads.dds")
    dds.files = []
    dds_app = types.ModuleType("keysight.ads.dds.app")
    dds_app.register_window_callback = lambda callback: registered.setdefault("window", ("window-token", callback))[0]
    dds_app.register_popup_callback = lambda callback: registered.setdefault("popup", ("popup-token", callback))[0]
    dds_app.unregister_window_callback = lambda token: unregistered.append(("window", token))
    dds_app.unregister_popup_callback = lambda token: unregistered.append(("popup", token))
    dds_app.WindowChange = SimpleNamespace(OPENED="opened")
    _keysight_modules(monkeypatch, dds=dds, dds_app=dds_app)

    registry = context.ContextRegistry("dds", slot="unit")
    ui = context_ui.ContextUi("dds", registry)
    ui.setup()
    popup = Menu()
    dds_file = SimpleNamespace(data_path="C:/demo_wrk/data/report.dds", name="report", selected_objects=[])
    window = SimpleNamespace(current_page=SimpleNamespace(name="Main"))
    registered["popup"][1](popup, dds_file, window, object())
    popup.find_action(context_ui.ACTION_NAME).triggered.emit()

    captured = registry.list()[0]
    assert captured["selection"]["count"] == 0
    assert captured["target"]["kind"] == "dds-page"
    assert clipboard.text.startswith("EDA_CONTEXT:v1:")
    ui.stop()
    assert ("popup", "popup-token") in unregistered
    assert ("window", "window-token") in unregistered


def test_dds_opened_window_gets_owned_top_level_menu(monkeypatch):
    context, context_ui, _clipboard = _load_modules(monkeypatch)
    registered = {}
    main_window = MainWindow()
    dds = types.ModuleType("keysight.ads.dds")
    dds_app = types.ModuleType("keysight.ads.dds.app")
    dds_app.register_window_callback = lambda callback: registered.setdefault("window", callback) or callback
    dds_app.register_popup_callback = lambda callback: registered.setdefault("popup", callback) or callback
    dds_app.unregister_window_callback = lambda token: None
    dds_app.unregister_popup_callback = lambda token: None
    dds_app.WindowChange = SimpleNamespace(OPENED="opened")
    dds_app.get_pyside_main_window = lambda window: main_window
    _keysight_modules(monkeypatch, dds=dds, dds_app=dds_app)

    registry = context.ContextRegistry("dds", slot="unit")
    ui = context_ui.ContextUi("dds", registry)
    ui.setup()
    dds_file = SimpleNamespace(data_path="C:/demo_wrk/data/report.dds", name="report", selected_objects=[])
    window = SimpleNamespace(current_page=SimpleNamespace(name="Main"))
    registered["window"](dds_file, window, dds_app.WindowChange.OPENED)

    menu_action = main_window.menubar.find_action(context_ui.MENU_NAME)
    assert menu_action is not None
    assert menu_action.menu().objectName() == context_ui.QT_MENU_OBJECT_NAME
    assert menu_action.menu().find_action(context_ui.ACTION_NAME) is not None
