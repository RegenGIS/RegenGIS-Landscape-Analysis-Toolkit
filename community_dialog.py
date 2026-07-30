import os

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QPixmap, QDesktopServices
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget


class CommunityDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Join the RegenGIS Community")
        self.setMinimumWidth(450)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(plugin_dir, "logo_regengis.png")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        banner = QLabel()
        banner.setStyleSheet("background-color: #158C78;")
        banner.setFixedHeight(120)

        banner_layout = QVBoxLayout(banner)
        banner_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if os.path.exists(logo_path):
            logo_label = QLabel()
            pixmap = QPixmap(logo_path)
            scaled = pixmap.scaled(200, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            banner_layout.addWidget(logo_label)

        main_layout.addWidget(banner)

        content_widget = QLabel(
            "Thank you for installing the RegenGIS plugin.\n\n"
            "We’re excited to support your work in regenerative landscape design.\n\n"
            "Join the RegenGIS community to:\n\n"
            "• stay informed about new plugin features and updates\n"
            "• discover new learning resources and practical workflows\n"
            "• hear about upcoming courses and training opportunities\n"
            "• connect with others exploring GIS for regenerative design\n\n"
            "Would you like to join the community?"
        )
        content_widget.setStyleSheet(
            "background-color: #FFFFFF; "
            "color: #333333; "
            "padding: 20px; "
            "font-size: 13px;"
        )
        content_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_widget.setWordWrap(True)
        main_layout.addWidget(content_widget)

        buttons_widget = QWidget()
        buttons_widget.setStyleSheet("background-color: #FFFFFF; padding: 15px;")
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setSpacing(15)

        join_btn = QPushButton("Yes, I’d love to join")
        join_btn.setStyleSheet("""
            QPushButton {
                background-color: #158C78;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 13px;
                font-weight: bold;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #127a66;
            }
            QPushButton:pressed {
                background-color: #0f6554;
            }
        """)

        no_btn = QPushButton("No Thanks")
        no_btn.setStyleSheet("""
            QPushButton {
                background-color: #E3EBEB;
                color: #555555;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 13px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #d4dfdf;
            }
            QPushButton:pressed {
                background-color: #c5d3d3;
            }
        """)

        buttons_layout.addStretch()
        buttons_layout.addWidget(join_btn)
        buttons_layout.addWidget(no_btn)
        buttons_layout.addStretch()

        main_layout.addWidget(buttons_widget)

        join_btn.clicked.connect(self._on_join_clicked)
        no_btn.clicked.connect(self.reject)

    def _on_join_clicked(self):
        QDesktopServices.openUrl(QUrl("https://www.regengis.com/account/registration/new"))
        self.accept()