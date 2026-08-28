"""DE and DDS menu adapters for bounded ADS context capture."""

from __future__ import annotations

try:
    from PySide6 import QtWidgets
except ImportError:
    try:
        from PySide2 import QtWidgets
    except ImportError:
        from qtpy import QtWidgets


MENU_NAME = "ADS Context"
ACTION_NAME = "Copy ADS Context"
DE_POPUP_CALLBACK = "AdsAgentBridge.Context.DesignPopup"
DE_MAIN_POPUP_CALLBACK = "AdsAgentBridge.Context.WorkspacePopup"
QT_MENU_OBJECT_NAME = "AdsAgentBridge.Context.Menu"
QT_ACTION_OBJECT_NAME = "AdsAgentBridge.Context.Action"


def _safe_call(value, name, *args):
    method = getattr(value, name, None)
    if not callable(method):
        return None
    return method(*args)


class ContextUi:
    """Own callback registrations and menu objects for one ADS profile."""

    def __init__(self, profile, registry):
        self.profile = profile
        self.registry = registry
        self._de_app = None
        self._de_module = None
        self._de_app_module = None
        self._dds_module = None
        self._dds_app = None
        self._dds_callbacks = []
        self._de_menus = []
        self._last_error = None
        self._surfaces = {}

    def setup(self, addon=None):
        del addon
        try:
            if self.profile == "de":
                self._setup_de()
            elif self.profile == "dds":
                self._setup_dds()
            else:
                raise ValueError("unsupported ADS UI profile: {0}".format(self.profile))
        except Exception:
            self.stop()
            raise
        self._publish_status("ready")

    def stop(self):
        if self.profile == "de":
            self._stop_de()
        elif self.profile == "dds":
            self._stop_dds()
        self._publish_status("stopped")

    def status(self):
        return {
            "state": "error" if self._last_error else "ready",
            "profile": self.profile,
            "last_error": self._last_error,
            "de_popup_registered": self._de_app is not None if self.profile == "de" else False,
            "dds_callback_count": len(self._dds_callbacks),
            "surfaces": dict(self._surfaces),
        }

    def _publish_status(self, state):
        status = self.status()
        status["state"] = state if not self._last_error else "error"
        self.registry.set_ui_status(status)

    def _guard(self, callback):
        def wrapped(*args, **kwargs):
            try:
                return callback(*args, **kwargs)
            except Exception as exc:
                self._last_error = str(exc)
                self._publish_status("error")
                print("ADS Agent Bridge context action failed: {0}".format(exc))
                return None

        return wrapped

    def _copy(self, envelope):
        text = envelope.get("eda_context_ref", envelope["context_ref"])["text"]
        application = QtWidgets.QApplication.instance()
        if application is None:
            raise RuntimeError("Qt application is unavailable")
        clipboard = application.clipboard()
        if clipboard is None:
            raise RuntimeError("Qt clipboard is unavailable")
        clipboard.setText(text)
        print("ADS Agent context copied: {0}".format(text))
        return envelope

    # -- Design Environment -------------------------------------------------

    def _setup_de(self):
        from keysight.ads import de
        from keysight.ads.de import app as de_app

        self._de_module = de
        self._de_app_module = de_app
        self._de_app = de_app.Application()
        self._remove_de_callbacks()
        self._de_app.add_popup_callback(self._guard(self._de_popup), DE_POPUP_CALLBACK)
        self._de_app.add_main_popup_callback(self._guard(self._de_main_popup), DE_MAIN_POPUP_CALLBACK)
        experimental = getattr(self._de_app_module, "experimental", None)
        self._surfaces = {
            "design-window": "available",
            "workspace-tree": (
                "available"
                if callable(getattr(experimental, "selected_workspace_items", None))
                else "unavailable"
            ),
        }

    def _remove_de_callbacks(self):
        if self._de_app is None:
            return
        for method_name, callback_name in (
            ("remove_popup_callback", DE_POPUP_CALLBACK),
            ("remove_main_popup_callback", DE_MAIN_POPUP_CALLBACK),
        ):
            try:
                _safe_call(self._de_app, method_name, callback_name)
            except Exception:
                pass

    def _stop_de(self):
        self._remove_de_callbacks()
        self._de_menus = []
        self._de_app = None

    def _design_from_window(self, window):
        design = self._de_app_module.get_design_in_uu_from_window(window)
        if design is None:
            raise RuntimeError("the selected ADS window has no editable design")
        return design

    def _capture_de_window(self, window):
        return self._copy(self.registry.capture_design(self._design_from_window(window), window))

    def _de_action(self, action, window):
        del action
        return self._capture_de_window(window)

    def _supported_de_window(self, window_or_definition):
        window_type = getattr(window_or_definition, "window_type", None)
        window_types = self._de_app_module.WindowType
        supported = {
            value
            for value in (
                getattr(window_types, "SCHEMATIC_WINDOW", None),
                getattr(window_types, "LAYOUT_WINDOW", None),
                getattr(window_types, "SYMBOL_WINDOW", None),
            )
            if value is not None
        }
        return window_type in supported

    def _replace_native_action(self, menu):
        existing = _safe_call(menu, "find_action", ACTION_NAME)
        if existing is not None:
            _safe_call(menu, "remove_action", existing)
        action = self._de_app_module.Action(ACTION_NAME, self._guard(self._de_action), None)
        menu.add_action(action)

    def generate_de_menu(self, addon, win_def):
        del addon
        if not self._supported_de_window(win_def):
            return
        menubar = getattr(win_def, "menubar", None)
        tools_menu = _safe_call(menubar, "find_menu", "Tools") if menubar is not None else None
        if tools_menu is None:
            return
        context_menu = _safe_call(tools_menu, "find_menu", MENU_NAME)
        if context_menu is None:
            context_menu = self._de_app_module.Menu(MENU_NAME)
            tools_menu.add_menu(context_menu)
        self._replace_native_action(context_menu)
        if context_menu not in self._de_menus:
            self._de_menus.append(context_menu)

    def _de_popup(self, popup_menu, window):
        if not self._supported_de_window(window):
            return
        self._replace_native_action(popup_menu)

    def _workspace_path(self):
        try:
            if self._de_module.workspace_is_open():
                return str(self._de_module.active_workspace().path)
        except Exception:
            pass
        return ""

    def _de_main_popup(self, popup_menu, widget):
        del widget
        experimental = getattr(self._de_app_module, "experimental", None)
        selected = _safe_call(experimental, "selected_workspace_items") if experimental is not None else None
        try:
            captured = tuple(selected or ())
        except Exception:
            captured = ()
        if not captured:
            return
        self._remove_qt_action(popup_menu)
        action = popup_menu.addAction(ACTION_NAME)
        _safe_call(action, "setObjectName", QT_ACTION_OBJECT_NAME)
        workspace_path = self._workspace_path()
        action.triggered.connect(
            self._guard(
                lambda *_ignored, items=captured, workspace=workspace_path: self._copy(
                    self.registry.capture_workspace_items(items, workspace)
                )
            )
        )

    # -- Data Display -------------------------------------------------------

    def _setup_dds(self):
        from keysight.ads import dds
        from keysight.ads.dds import app as dds_app

        self._dds_module = dds
        self._dds_app = dds_app
        self._register_dds_callback("window", self._guard(self._dds_window_callback))
        self._register_dds_callback("popup", self._guard(self._dds_popup_callback))
        self._surfaces = {"dds-window": "available"}

    def _register_dds_callback(self, kind, callback):
        register = getattr(self._dds_app, "register_{0}_callback".format(kind))
        token = register(callback)
        self._dds_callbacks.append((kind, token, callback))

    def _stop_dds(self):
        for kind, token, callback in reversed(self._dds_callbacks):
            unregister = getattr(self._dds_app, "unregister_{0}_callback".format(kind), None)
            if not callable(unregister):
                continue
            try:
                unregister(token if token is not None else callback)
            except Exception:
                try:
                    unregister(callback)
                except Exception:
                    pass
        self._dds_callbacks = []

    def _dds_window_callback(self, dds_file, window, change):
        opened = getattr(self._dds_app.WindowChange, "OPENED", None)
        if change is opened or change == opened:
            self._add_dds_window_menu(dds_file, window)

    def _remove_qt_action(self, menu):
        for action in list(menu.actions()):
            try:
                if action.objectName() == QT_ACTION_OBJECT_NAME:
                    menu.removeAction(action)
            except Exception:
                pass

    def _add_dds_window_menu(self, dds_file, window):
        main_window = self._dds_app.get_pyside_main_window(window)
        if main_window is None:
            return
        menubar = main_window.menuBar()
        context_menu = menubar.addMenu(MENU_NAME)
        context_menu.setObjectName(QT_MENU_OBJECT_NAME)
        action = context_menu.addAction(ACTION_NAME)
        _safe_call(action, "setObjectName", QT_ACTION_OBJECT_NAME)
        action.triggered.connect(
            self._guard(lambda *_ignored, file=dds_file, win=window: self._capture_dds(file, win))
        )

    def _capture_dds(self, dds_file, window):
        return self._copy(self.registry.capture_dds(dds_file, window))

    def _dds_popup_callback(self, menu, dds_file, window, position):
        del position
        if dds_file is None or window is None:
            return
        self._remove_qt_action(menu)
        action = menu.addAction(ACTION_NAME)
        _safe_call(action, "setObjectName", QT_ACTION_OBJECT_NAME)
        action.triggered.connect(
            self._guard(lambda *_ignored, file=dds_file, win=window: self._capture_dds(file, win))
        )
