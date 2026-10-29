"""Shared themes for native dialogs; web palettes use the same semantic values."""
import re
from PySide6.QtGui import QColor, QPalette

PALETTES = {
    'dark': dict(background='#111417', surface='#171b20', raised='#1d252d', hover='#29343e', text='#edf0f4', secondary='#bdc6d1', muted='#9faebb', border='#35424e', strong='#647482', accent='#d7bc94', accent_text='#201b15', soft='#302a22', danger='#f2b2b0', danger_soft='#462b2d'),
    'black': dict(background='#000000', surface='#000000', raised='#0b0b0b', hover='#202020', text='#f6f6f6', secondary='#cecece', muted='#ababab', border='#333333', strong='#757575', accent='#e0c59f', accent_text='#17120e', soft='#241f19', danger='#f0b7b7', danger_soft='#301818'),
    'light': dict(background='#ffffff', surface='#ffffff', raised='#f2f4f6', hover='#e5e9ed', text='#17212b', secondary='#384b5b', muted='#506273', border='#bdc7d0', strong='#6c7e8d', accent='#705020', accent_text='#ffffff', soft='#f4eadb', danger='#a12a2f', danger_soft='#fae5e5'),
    'mono': dict(background='#000000', surface='#090909', raised='#171717', hover='#292929', text='#ffffff', secondary='#d0d0d0', muted='#aaaaaa', border='#444444', strong='#888888', accent='#ffffff', accent_text='#000000', soft='#292929', danger='#ffffff', danger_soft='#333333'),
}

STYLE = """
QWidget { background: #17212b; color: #f1f3f5; font-family: 'Manrope', 'Segoe UI Variable', 'Segoe UI'; font-size: 14px; }
QLabel { background: transparent; border: none; }
QLabel#WindowTitle { font-size: 18px; font-weight: 600; }
QLabel#LauncherTitle { font-size: 22px; font-weight: 600; }
QLabel#Heading, QLabel#SectionTitle { font-size: 16px; font-weight: 600; }
QLabel#Muted, QLabel#muted, QLabel#subtitle, QLabel#SearchSubtitle { color: #a6b2bf; font-size: 13px; }
QLabel#SmallMuted { color: #a0adba; font-size: 12px; }
QLabel#ProviderStatus { color: #b5c4d2; font-size: 13px; }
QLabel#ChatPrivacy { color: #a6b2bf; font-size: 12px; background: #17212b; }
QLabel#TypingStatus { color: #a6b2bf; font-size: 12px; background: #0e1621; }
QLabel#ProcessStatus, QLabel#Detection { color: #a8c8e7; font-size: 13px; }
QLabel#SearchStatus { color: #b5c1ce; font-size: 13px; padding: 0; }
QLabel#ResultCount { color: #f1f3f5; font-size: 14px; font-weight: 600; }
QLabel#EmptyState, QLabel#ChatEmptyState { color: #a6b2bf; font-size: 14px; padding: 10px; }
QLabel#Caution { color: #d6b58b; font-size: 13px; }
QLabel#QueryPreview { color: #d4dee7; font-family: 'Consolas'; font-size: 13px; padding: 6px; background: #202b36; }
QWidget#OsintPanel, QWidget#SettingsDialog { border: 1px solid #30404e; }
QWidget#WindowHeader { background: #17212b; border: none; border-bottom: 1px solid #30404e; }
QWidget#WindowHeader QWidget { background: transparent; border: none; }
QWidget#ChatPage, QWidget#ChatHeader { background: #17212b; }
QWidget#ComposerArea { background: #17212b; border-top: 1px solid #30404e; }
QFrame#ChatComposer { background: #242f3d; border: 1px solid #344757; border-radius: 20px; }
QPlainTextEdit#ChatComposerInput { background: transparent; border: none; padding: 12px 1px 10px 1px; font-size: 14px; }
QPushButton#ChatSendButton { background: transparent; border: none; padding: 0; }
QScrollArea#MessageHistory, QWidget#MessageViewport { background: #0e1621; border: none; }
QWidget#MessageBody, QWidget#MessageRow { background: transparent; }
QWidget#BubbleActions { background: transparent; }
QWidget#CanvasWorkspace { background: #0e1621; }
QWidget#CanvasHeader { background: #17212b; border-bottom: 1px solid #30404e; }
QTextBrowser#MarkdownDocument, QPlainTextEdit#CanvasEditor { background: #0e1621; border: none; color: #f1f3f5; padding: 0; }
QListWidget#CanvasOutline { background: #17212b; border: none; border-right: 1px solid #30404e; padding: 7px; }
QListWidget#CanvasOutline::item { padding: 6px 3px; color: #b5c4d2; }
QListWidget#CanvasOutline::item:selected { background: #243442; color: #f1f3f5; }
QFrame#IncomingBubble { background: #182533; border: none; border-radius: 13px; }
QFrame#OutgoingBubble { background: #2b5278; border: none; border-radius: 13px; }
QFrame#StatusBubble { background: #252b38; border: 1px solid #475263; border-radius: 11px; }
QTextBrowser#BubbleText, QTextBrowser#BubbleText QWidget { background: transparent; border: none; padding: 0; color: #f1f3f5; font-size: 14px; }
QPushButton { background: #202b36; color: #f1f3f5; border: 1px solid #344757; border-radius: 7px; padding: 7px 12px; }
QPushButton:hover { background: #2b3a49; border-color: #52708b; }
QPushButton:pressed { background: #1a2836; }
QPushButton:disabled { background: #202b36; color: #788796; border-color: #2b3b48; }
QPushButton#PrimaryButton, QPushButton#primary { background: #487ba9; color: #ffffff; border-color: #487ba9; font-weight: 600; }
QPushButton#PrimaryButton:hover, QPushButton#primary:hover { background: #588cbb; border-color: #588cbb; }
QPushButton#PrimaryButton:disabled, QPushButton#primary:disabled { background: #2d465e; color: #91a4b6; border-color: #2d465e; }
QPushButton#QuietButton, QPushButton#quiet { background: transparent; border-color: transparent; color: #a9c6e0; padding: 5px 7px; }
QPushButton#QuietButton:hover, QPushButton#quiet:hover { color: #f1f3f5; background: #243442; }
QPushButton#ChoiceButton { background: #202b36; border-color: #344757; color: #d0dbe5; padding: 6px 9px; font-size: 13px; }
QPushButton#ChoiceButton:checked { border-color: #6c9ed2; color: #e7f1fa; background: #2b4055; }
QToolButton { background: #202b36; color: #c0cdda; border: 1px solid #344757; border-radius: 6px; padding: 5px 8px; }
QToolButton:hover { background: #2a3b4b; color: #f1f3f5; }
QToolButton#WindowControl, QToolButton#WindowClose { background: transparent; border: none; font-size: 20px; padding: 0; }
QToolButton#WindowControl:hover { background: #293b4b; }
QToolButton#WindowClose:hover { background: #653f48; color: #ffffff; }
QToolButton#Disclosure, QToolButton#InlineAction { background: transparent; border: none; color: #a9c9e8; font-size: 13px; padding: 4px 0; }
QToolButton#Disclosure:hover, QToolButton#InlineAction:hover { color: #d0e6fb; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTextBrowser { background: #242f3d; color: #f1f3f5; border: 1px solid #344757; border-radius: 6px; padding: 6px 8px; selection-background-color: #4777a5; }
QLineEdit#MainQuery { background: #242f3d; border-color: #344757; font-size: 14px; padding: 8px 10px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus { border-color: #6c9ed2; }
QLineEdit:disabled { color: #788796; }
QLineEdit#AddressSummary { background: transparent; color: #b5c3d0; border: none; padding: 1px 0; font-size: 13px; }
QComboBox { padding-right: 25px; }
QComboBox::drop-down { border: none; width: 23px; }
QComboBox QAbstractItemView { background: #202b36; color: #f1f3f5; selection-background-color: #2b5278; border: 1px solid #425b70; padding: 3px; }
QSpinBox { padding-right: 18px; }
QCheckBox { background: transparent; spacing: 7px; }
QCheckBox::indicator { width: 15px; height: 15px; background: #242f3d; border: 1px solid #647d93; border-radius: 3px; }
QCheckBox::indicator:checked { background: #6c9ed2; border-color: #6c9ed2; }
QSlider::groove:horizontal { height: 3px; background: #344757; }
QSlider::sub-page:horizontal { background: #6c9ed2; }
QSlider::handle:horizontal { width: 12px; margin: -5px 0; border-radius: 6px; background: #8eb9e0; }
QFrame#separator { max-height: 1px; border: none; background: #30404e; }
QScrollArea, QScrollArea > QWidget > QWidget { border: none; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 0; }
QScrollBar::handle:vertical { min-height: 25px; background: #3c5367; border-radius: 3px; }
QScrollBar::handle:vertical:hover { background: #58758e; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QMenu { background: #202b36; color: #f1f3f5; border: 1px solid #42596d; padding: 4px; }
QMenu::item { padding: 6px 13px; }
QMenu::item:selected { background: #2b5278; }
QMenu::separator { height: 1px; background: #30404e; margin: 4px; }
QToolTip { background: #293c4d; color: #f1f3f5; border: 1px solid #58758e; padding: 5px 8px; }
QListView#EvidenceList { background: #17212b; border: none; outline: none; padding: 0; }
QListView#EvidenceList::item { border: none; }
QProgressBar { border: none; background: #243442; }
QProgressBar::chunk { background: #6c9ed2; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #b2c1cf; padding: 9px 15px; border: none; border-bottom: 2px solid transparent; font-size: 14px; }
QTabBar::tab:selected { color: #f1f3f5; border-bottom-color: #6c9ed2; }
QTabBar#ModeTabs::tab:selected { border-bottom-color: transparent; }
QTabBar::tab:hover { background: #202b36; color: #f1f3f5; }
QTableWidget { background: #202b36; border: none; gridline-color: #30404e; selection-background-color: #2b4055; }
QHeaderView::section { background: #243442; color: #c6d5e3; border: none; padding: 6px; }
"""


def style_for_theme(theme='dark'):
    """Resolve legacy native declarations through a small semantic palette."""
    palette = PALETTES.get(theme, PALETTES['dark'])

    def declaration(match):
        prop, value = match.group(1), match.group(2)
        def colour(found):
            original = found.group(0)
            color = QColor(original)
            _, saturation, brightness, _ = color.getHsvF()
            if 'border' in prop or 'gridline' in prop:
                return palette['border']
            if prop in ('background', 'selection-background-color'):
                return palette['background'] if brightness < .14 else palette['surface'] if brightness < .22 else palette['raised'] if brightness < .3 else palette['hover']
            if prop == 'color':
                return palette['text'] if brightness > .83 else palette['secondary'] if brightness > .6 else palette['muted']
            return original
        return prop + ':' + re.sub(r'#[0-9a-fA-F]{6}\b', colour, value)

    sheet = re.sub(r'([a-zA-Z-]+):([^;{}]+)', declaration, STYLE)
    sheet += f"""
QPushButton#PrimaryButton, QPushButton#primary {{ background: {palette['accent']}; color: {palette['accent_text']}; border-color: {palette['accent']}; }}
QPushButton#PrimaryButton:hover, QPushButton#primary:hover {{ background: {palette['accent']}; color: {palette['accent_text']}; }}
QWidget:focus, QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {palette['accent']}; }}
QToolButton#WindowClose:hover {{ background: {palette['danger_soft']}; }}
"""
    return sheet


def apply_theme(app, theme='dark'):
    """Change only this Qt application's palette and existing native surfaces."""
    selected = theme if theme in PALETTES else 'dark'
    colors = PALETTES[selected]
    palette = QPalette()
    for role, name in ((QPalette.ColorRole.Window, 'surface'), (QPalette.ColorRole.WindowText, 'text'),
                       (QPalette.ColorRole.Base, 'background'), (QPalette.ColorRole.AlternateBase, 'raised'),
                       (QPalette.ColorRole.Text, 'text'), (QPalette.ColorRole.Button, 'raised'),
                       (QPalette.ColorRole.ButtonText, 'text'), (QPalette.ColorRole.Highlight, 'accent'),
                       (QPalette.ColorRole.HighlightedText, 'accent_text'), (QPalette.ColorRole.PlaceholderText, 'muted')):
        palette.setColor(role, QColor(colors[name]))
    app.setPalette(palette)
    app.setProperty('granger_theme', selected)
    app.setStyleSheet(style_for_theme(selected))
    # OsintPanel historically set a local copy of STYLE, which would mask the app palette.
    for widget in app.topLevelWidgets():
        if widget.objectName() in ('OsintPanel', 'SettingsDialog') and widget.styleSheet():
            widget.setStyleSheet(style_for_theme(selected))
        widget.update()
    return selected
