#!/usr/bin/env python3
"""The bar's application menu, opened by the Tux icon, in the Midnight Ink theme.

Type to search; arrows and Enter to start an app; Esc or a click elsewhere
closes it. The menu keeps running hidden, so it opens instantly:

  appmenu.py           run the menu (hidden until toggled)
  appmenu.py --show    run it and open it straight away

The `menu` script toggles it (and starts it if it isn't running).
"""
import os
import subprocess
import sys

os.environ["QT_QPA_PLATFORM"] = "xcb"          # XWayland, so the menu can sit under the bar

from PySide6.QtCore import QEvent, QSize, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QIcon  # noqa: E402
from PySide6.QtNetwork import QLocalServer  # noqa: E402
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,  # noqa: E402
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QToolButton,
                               QVBoxLayout, QWidget)

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from common import RUNTIME_DIR, SCRIPTS, THEME, load_config  # noqa: E402

SOCKET = os.path.join(RUNTIME_DIR, "kbar-menu.sock")
BAR_HEIGHT = 41                                 # config.ini height + border
T = THEME

CATEGORIES = [  # (name, glyph, freedesktop main categories)
    ("All", "\U000f003b", None),
    ("Favourites", "\U000f04ce", None),
    ("Development", "\U000f0169", {"Development"}),
    ("Internet", "\U000f059f", {"Network"}),
    ("Multimedia", "\U000f0387", {"AudioVideo", "Audio", "Video"}),
    ("Graphics", "\U000f03d8", {"Graphics"}),
    ("Office", "\U000f0219", {"Office"}),
    ("Games", "\U000f0297", {"Game"}),
    ("Education", "\U000f0474", {"Education", "Science"}),
    ("Settings", "\U000f0493", {"Settings"}),
    ("System", "\U000f048b", {"System"}),
    ("Utilities", "\U000f05b7", {"Utility"}),
    ("Other", "\U000f01d8", set()),
]


# -- .desktop files ------------------------------------------------------------
def app_dirs():
    home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    dirs = (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    extra = [os.path.expanduser("~/.local/share/flatpak/exports/share"), "/var/lib/flatpak/exports/share"]
    seen, out = set(), []
    for d in [home] + dirs + extra:
        path = os.path.join(d, "applications")
        if path not in seen and os.path.isdir(path):
            seen.add(path)
            out.append(path)
    return out


def parse_desktop(path):
    entry, section = {}, None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("["):
                    section = line
                elif section == "[Desktop Entry]" and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    entry.setdefault(k.strip(), v.strip())
    except OSError:
        pass
    return entry


def localized(entry, key):
    lang = (os.environ.get("LANG") or "C").split(".")[0]
    for k in (f"{key}[{lang}]", f"{key}[{lang.split('_')[0]}]", key):
        if entry.get(k):
            return entry[k]
    return ""


def load_apps():
    """{desktop id: app dict}; the first directory that defines an id wins."""
    apps, desktop = {}, "KDE"
    for base in app_dirs():
        for root, _, files in os.walk(base):
            for name in files:
                if not name.endswith(".desktop"):
                    continue
                path = os.path.join(root, name)
                app_id = os.path.relpath(path, base)[:-8].replace("/", "-")
                if app_id in apps:
                    continue
                e = parse_desktop(path)
                apps[app_id] = None                       # hidden entries still shadow later ones
                if e.get("Type") != "Application" or e.get("NoDisplay") == "true" or e.get("Hidden") == "true":
                    continue
                if e.get("OnlyShowIn") and desktop not in e["OnlyShowIn"].split(";"):
                    continue
                if desktop in e.get("NotShowIn", "").split(";"):
                    continue
                cats = set(filter(None, e.get("Categories", "").split(";")))
                apps[app_id] = {
                    "id": app_id, "name": localized(e, "Name") or app_id,
                    "generic": localized(e, "GenericName"), "comment": localized(e, "Comment"),
                    "keywords": localized(e, "Keywords").replace(";", " "), "icon": e.get("Icon", ""),
                    "cats": cats, "exec": os.path.basename(e.get("Exec", "").split(" ")[0]),
                }
    return {k: v for k, v in apps.items() if v}


def category_of(app):
    for name, _, cats in CATEGORIES[2:-1]:
        if app["cats"] & cats:
            return name
    return "Other"


# -- the menu --------------------------------------------------------------------
STYLE = f"""
QFrame#card {{ background: {T['bg']}; border: 1px solid {T['edge']}; border-radius: 12px; }}
QLineEdit {{ background: {T['card']}; color: {T['fg']}; border: 1px solid {T['edge']}; border-radius: 9px;
             padding: 8px 12px; selection-background-color: {T['track']}; }}
QLineEdit:focus {{ border-color: {T['lavender']}; }}
QListWidget {{ background: transparent; border: none; outline: none; color: {T['fg']}; }}
QListWidget::item {{ padding: 6px 8px; border-radius: 8px; }}
QListWidget::item:hover {{ background: {T['card']}; }}
QListWidget::item:selected {{ background: {T['track']}; color: {T['fg']}; }}
QListWidget#cats {{ color: {T['label']}; }}
QListWidget#cats::item:selected {{ color: {T['lavender']}; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {T['track']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 4px 8px; }}
QToolButton:hover {{ background: {T['card']}; }}
QLabel#hint {{ color: {T['label']}; }}
QLabel#user {{ color: {T['rose']}; }}
"""


class Menu(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setWindowTitle("kbar-menu")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self.resize(640, 540)
        self.apps, self.favourites = {}, []
        self.icons, self.apps_stamp = {}, None

        family = "FantasqueSansM Nerd Font"
        self.setFont(QFont(family, 11))
        card = QFrame(self, objectName="card")
        shadow = QGraphicsDropShadowEffect(blurRadius=24, offset=0, color=QColor(0, 0, 0, 160))
        card.setGraphicsEffect(shadow)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 4, 10, 14)        # room for the shadow
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 14, 14, 10)
        lay.setSpacing(10)
        self.search = QLineEdit(placeholderText="\U000f0349  Search applications")
        self.search.textChanged.connect(self.refresh)
        self.search.installEventFilter(self)
        lay.addWidget(self.search)

        body = QHBoxLayout()
        body.setSpacing(8)
        self.cats = QListWidget(objectName="cats")
        self.cats.setFixedWidth(170)
        self.cats.currentRowChanged.connect(lambda _: self.refresh())
        self.list = QListWidget()
        self.list.setIconSize(QSize(28, 28))
        self.list.itemActivated.connect(self.launch)
        self.list.itemClicked.connect(self.launch)
        self.list.currentItemChanged.connect(self.describe)
        self.list.installEventFilter(self)
        body.addWidget(self.cats)
        body.addWidget(self.list, 1)
        lay.addLayout(body, 1)

        self.hint = QLabel(objectName="hint")
        self.hint.setFont(QFont(family, 10))
        lay.addWidget(self.hint)

        foot = QHBoxLayout()
        self.user = QLabel(objectName="user")
        foot.addWidget(self.user)
        foot.addStretch(1)
        kde = os.path.join(SCRIPTS, "kde")
        for glyph, tip, c, cmd in (("\U000f033e", "Lock", "sky", f"{kde} lock"),
                                   ("\U000f0343", "Log out", "butter", f"{kde} logout"),
                                   ("\U000f0709", "Restart", "lavender", f"{kde} reboot"),
                                   ("\U000f0425", "Shut down", "coral", f"{kde} shutdown")):
            b = QToolButton(text=glyph, toolTip=tip)
            b.setFont(QFont(family, 15))
            b.setStyleSheet(f"color: {T[c]};")
            b.clicked.connect(lambda _=False, cmd=cmd: self.run(cmd))
            foot.addWidget(b)
        lay.addLayout(foot)

    # -- data --
    def reload(self):
        label = str(load_config().get("menu", {}).get("user_label", "")).strip()
        self.user.setText("\U000f0009  " + (label or f"{os.environ.get('USER', '')}@{os.uname().nodename}"))
        stamp = [os.stat(d).st_mtime_ns for d in app_dirs()]   # rescan only after installs/removals
        if stamp != self.apps_stamp:
            self.apps, self.apps_stamp = load_apps(), stamp
        favs = [e.get("desktop", "").removesuffix(".desktop") for e in load_config().get("launcher", [])]
        self.favourites = [f for f in favs if f in self.apps]
        present = {category_of(a) for a in self.apps.values()}
        self.cats.blockSignals(True)
        self.cats.clear()
        for name, glyph, _ in CATEGORIES:
            if name in ("All", "Favourites") or name in present:
                item = QListWidgetItem(f"{glyph}   {name}")
                item.setData(Qt.ItemDataRole.UserRole, name)
                self.cats.addItem(item)
        self.cats.setCurrentRow(0)
        self.cats.blockSignals(False)

    def refresh(self):
        q = self.search.text().strip().lower()
        cat = self.cats.currentItem().data(Qt.ItemDataRole.UserRole) if self.cats.currentItem() else "All"
        if q:
            def rank(a):
                name = a["name"].lower()
                if name.startswith(q):
                    return 0
                if q in name:
                    return 1
                hay = " ".join((a["generic"], a["keywords"], a["comment"], a["exec"])).lower()
                return 2 if q in hay else None
            hits = [(r, a) for a in self.apps.values() if (r := rank(a)) is not None]
            shown = [a for _, a in sorted(hits, key=lambda x: (x[0], x[1]["name"].lower()))]
        elif cat == "Favourites":
            shown = [self.apps[f] for f in self.favourites]
        else:
            shown = sorted((a for a in self.apps.values() if cat == "All" or category_of(a) == cat),
                           key=lambda a: a["name"].lower())
        self.list.clear()
        for a in shown:
            item = QListWidgetItem(self.icon(a["icon"]), a["name"])
            item.setData(Qt.ItemDataRole.UserRole, a["id"])
            self.list.addItem(item)
        if shown:
            self.list.setCurrentRow(0)
        else:
            self.hint.setText("No matching applications")

    def icon(self, name):
        """Theme lookups are slow (~5 ms each), so every icon is looked up once."""
        if name not in self.icons:
            if name.startswith("/"):
                self.icons[name] = QIcon(name)
            else:
                self.icons[name] = QIcon.fromTheme(name, QIcon.fromTheme("application-x-executable"))
        return self.icons[name]

    def warm(self):
        """Load the apps and their icons ahead of the first click."""
        self.reload()
        for a in self.apps.values():
            self.icon(a["icon"])

    def describe(self, item, _prev=None):
        a = self.apps.get(item.data(Qt.ItemDataRole.UserRole)) if item else None
        self.hint.setText((a["comment"] or a["generic"]) if a else "")

    # -- actions --
    def run(self, cmd):
        subprocess.Popen(cmd, shell=True, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.hide()

    def launch(self, item=None):
        item = item or self.list.currentItem()
        if item:
            self.run(f"{os.path.join(SCRIPTS, 'launch-app')} --desktop {item.data(Qt.ItemDataRole.UserRole)}")

    def toggle(self):
        if self.isVisible():
            self.hide()
            return
        self.reload()
        self.search.clear()
        self.refresh()
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.x(), screen.y() + BAR_HEIGHT)
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()

    # -- keyboard & focus --
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.KeyPress:
            key = ev.key()
            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.launch()
                return True
            if obj is self.search and key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
                QApplication.sendEvent(self.list, ev)
                return True
            if obj is self.list and ev.text().isprintable() and ev.text():
                self.search.setFocus()
                QApplication.sendEvent(self.search, ev)
                return True
        return super().eventFilter(obj, ev)

    def changeEvent(self, ev):
        if ev.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            QTimer.singleShot(120, lambda: None if self.isActiveWindow() else self.hide())
        super().changeEvent(ev)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    QIcon.setThemeSearchPaths(QIcon.themeSearchPaths() + [
        os.path.expanduser("~/.local/share/icons"), "/usr/share/icons",
        os.path.expanduser("~/.local/share/flatpak/exports/share/icons"), "/var/lib/flatpak/exports/share/icons"])
    QIcon.setThemeName(subprocess.run(["kreadconfig6", "--file", "kdeglobals", "--group", "Icons", "--key", "Theme"],
                                      capture_output=True, text=True).stdout.strip() or "breeze-dark")
    QIcon.setFallbackThemeName("hicolor")
    menu = Menu()
    QLocalServer.removeServer(SOCKET)
    server = QLocalServer()
    server.listen(SOCKET)

    def on_connection():
        conn = server.nextPendingConnection()
        conn.waitForReadyRead(200)
        if conn.readAll().data().strip() == b"toggle":
            menu.toggle()
        conn.disconnectFromServer()
    server.newConnection.connect(on_connection)
    if "--show" in sys.argv:
        QTimer.singleShot(0, menu.toggle)
    else:
        QTimer.singleShot(0, menu.warm)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
