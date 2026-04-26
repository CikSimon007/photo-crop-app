#!/usr/bin/env python3
"""
Orezavanie fotiek pre tlac
Hromadne orezavanie fotografii na zvoleny pomer stran pre tlac.
"""

import sys
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QComboBox, QSlider, QSpinBox, QCheckBox,
    QProgressBar, QMessageBox, QGroupBox, QFormLayout, QSizePolicy,
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QImage, QPainter, QColor, QPen, QPainterPath, QFont, QShortcut,
    QKeySequence,
)
from PIL import Image, ImageOps


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}
MAX_DISPLAY_SIZE = 2400

ASPECT_RATIOS = [
    ("3:2 (10x15 cm)", 3, 2),
    ("4:3", 4, 3),
    ("16:9", 16, 9),
    ("1:1 (stvorcovy)", 1, 1),
    ("5:4 (20x25 cm)", 5, 4),
    ("7:5 (13x18 cm)", 7, 5),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pil_to_qimage(pil_img: Image.Image) -> QImage:
    """Convert a PIL RGB Image to a QImage."""
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    data = pil_img.tobytes("raw", "RGB")
    qimg = QImage(data, pil_img.width, pil_img.height,
                  3 * pil_img.width, QImage.Format.Format_RGB888)
    return qimg.copy()


def scan_photos(directory: str) -> list[Path]:
    """Return sorted list of supported image files in *directory*."""
    return sorted(
        f for f in Path(directory).iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def adjusted_ratio(rw: int, rh: int, img_w: int, img_h: int) -> tuple[int, int]:
    """Swap ratio to match image orientation (landscape / portrait)."""
    if rw == rh:
        return rw, rh
    if (img_h > img_w) != (rh > rw):
        return rh, rw
    return rw, rh


def initial_crop(img_w: float, img_h: float,
                 rw: int, rh: int) -> QRectF:
    """Largest centred crop rectangle with aspect *rw*:*rh*."""
    target = rw / rh
    if img_w / img_h > target:
        crop_h = img_h
        crop_w = crop_h * target
    else:
        crop_w = img_w
        crop_h = crop_w / target
    return QRectF((img_w - crop_w) / 2, (img_h - crop_h) / 2, crop_w, crop_h)


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Orezavanie fotiek pre tlac")
        self.setMinimumWidth(520)
        self._input_dir = ""
        self._output_dir = ""
        self._build_ui()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)

        # Input
        grp = QGroupBox("Vstupny priecinok s fotkami")
        gl = QHBoxLayout()
        self.input_label = QLabel("Nevybrany")
        self.input_label.setWordWrap(True)
        btn = QPushButton("Vybrat...")
        btn.clicked.connect(self._pick_input)
        gl.addWidget(self.input_label, 1)
        gl.addWidget(btn)
        grp.setLayout(gl)
        lay.addWidget(grp)

        # Output
        grp = QGroupBox("Vystupny priecinok")
        gl = QHBoxLayout()
        self.output_label = QLabel("Nevybrany")
        self.output_label.setWordWrap(True)
        btn = QPushButton("Vybrat...")
        btn.clicked.connect(self._pick_output)
        gl.addWidget(self.output_label, 1)
        gl.addWidget(btn)
        grp.setLayout(gl)
        lay.addWidget(grp)

        # Settings
        grp = QGroupBox("Nastavenia")
        form = QFormLayout()

        self.ratio_combo = QComboBox()
        for name, _, _ in ASPECT_RATIOS:
            self.ratio_combo.addItem(name)
        form.addRow("Pomer stran:", self.ratio_combo)

        self.auto_orient_cb = QCheckBox("Automaticky prisposobit orientaciu")
        self.auto_orient_cb.setChecked(True)
        self.auto_orient_cb.setToolTip(
            "Pre fotky na vysku sa pomer automaticky otoci (napr. 3:2 -> 2:3)")
        form.addRow("", self.auto_orient_cb)

        qw = QWidget()
        ql = QHBoxLayout(qw)
        ql.setContentsMargins(0, 0, 0, 0)
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(95)
        self.quality_val = QLabel("95")
        self.quality_slider.valueChanged.connect(
            lambda v: self.quality_val.setText(str(v)))
        ql.addWidget(self.quality_slider, 1)
        ql.addWidget(self.quality_val)
        form.addRow("Kvalita JPEG:", qw)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 600)
        self.dpi_spin.setValue(300)
        self.dpi_spin.setSuffix(" DPI")
        form.addRow("DPI:", self.dpi_spin)

        grp.setLayout(form)
        lay.addWidget(grp)

        self.start_btn = QPushButton("Start")
        self.start_btn.setMinimumHeight(46)
        f = self.start_btn.font()
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        self.start_btn.setFont(f)
        self.start_btn.clicked.connect(self.accept)
        lay.addWidget(self.start_btn)

    # -- slots ---------------------------------------------------------------

    def _pick_input(self):
        p = QFileDialog.getExistingDirectory(self, "Vybrat vstupny priecinok")
        if p:
            self._input_dir = p
            self.input_label.setText(p)

    def _pick_output(self):
        p = QFileDialog.getExistingDirectory(self, "Vybrat vystupny priecinok")
        if p:
            self._output_dir = p
            self.output_label.setText(p)

    def accept(self):
        if not self._input_dir:
            QMessageBox.warning(self, "Chyba",
                                "Vyberte vstupny priecinok s fotkami.")
            return
        if not self._output_dir:
            QMessageBox.warning(self, "Chyba",
                                "Vyberte vystupny priecinok na ulozenie.")
            return
        if not scan_photos(self._input_dir):
            QMessageBox.warning(
                self, "Chyba",
                "Vo vybranom priecinku neboli najdene ziadne fotky.\n\n"
                f"Podporovane formaty: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
            return
        super().accept()

    def get_settings(self) -> dict:
        idx = self.ratio_combo.currentIndex()
        _, rw, rh = ASPECT_RATIOS[idx]
        return {
            "input_dir": self._input_dir,
            "output_dir": self._output_dir,
            "ratio_w": rw,
            "ratio_h": rh,
            "auto_orient": self.auto_orient_cb.isChecked(),
            "quality": self.quality_slider.value(),
            "dpi": self.dpi_spin.value(),
        }


# ---------------------------------------------------------------------------
# Crop editor widget
# ---------------------------------------------------------------------------

class CropEditor(QWidget):
    """Displays an image with a draggable, zoomable crop overlay."""

    crop_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        self.qimage: QImage | None = None
        self.crop_rect = QRectF()
        self.ratio_w = 3
        self.ratio_h = 2

        self._dragging = False
        self._drag_offset = QPointF()
        self._scale = 1.0
        self._off_x = 0.0
        self._off_y = 0.0

    # -- public api ----------------------------------------------------------

    def set_image(self, qimage: QImage, rw: int, rh: int):
        self.qimage = qimage
        self.ratio_w = rw
        self.ratio_h = rh
        self._calc_transform()
        self.crop_rect = initial_crop(qimage.width(), qimage.height(), rw, rh)
        self.update()

    def set_crop(self, rect: QRectF):
        self.crop_rect = rect
        self.update()

    # -- coordinate helpers --------------------------------------------------

    def _calc_transform(self):
        if not self.qimage:
            return
        iw, ih = self.qimage.width(), self.qimage.height()
        self._scale = min(self.width() / iw, self.height() / ih)
        self._off_x = (self.width() - iw * self._scale) / 2
        self._off_y = (self.height() - ih * self._scale) / 2

    def _to_display(self, r: QRectF) -> QRectF:
        return QRectF(r.x() * self._scale + self._off_x,
                      r.y() * self._scale + self._off_y,
                      r.width() * self._scale,
                      r.height() * self._scale)

    def _to_image(self, p: QPointF) -> QPointF:
        return QPointF((p.x() - self._off_x) / self._scale,
                       (p.y() - self._off_y) / self._scale)

    # -- max crop helpers ----------------------------------------------------

    def _max_crop_dims(self) -> tuple[float, float]:
        iw, ih = self.qimage.width(), self.qimage.height()
        target = self.ratio_w / self.ratio_h
        if iw / ih > target:
            return ih * target, ih
        return iw, iw / target

    # -- events --------------------------------------------------------------

    def resizeEvent(self, event):
        self._calc_transform()
        super().resizeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(35, 35, 35))
        if not self.qimage:
            p.end()
            return

        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        iw, ih = self.qimage.width(), self.qimage.height()
        dest = QRectF(self._off_x, self._off_y,
                      iw * self._scale, ih * self._scale)
        p.drawImage(dest, self.qimage)

        # Dark overlay outside crop
        cd = self._to_display(self.crop_rect)
        overlay = QPainterPath()
        overlay.addRect(QRectF(0, 0, self.width(), self.height()))
        hole = QPainterPath()
        hole.addRect(cd)
        overlay = overlay.subtracted(hole)
        p.fillPath(overlay, QColor(0, 0, 0, 150))

        # Crop border
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawRect(cd)

        # Rule-of-thirds grid
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        for i in range(1, 3):
            x = cd.x() + cd.width() * i / 3
            p.drawLine(int(x), int(cd.y()), int(x), int(cd.bottom()))
            y = cd.y() + cd.height() * i / 3
            p.drawLine(int(cd.x()), int(y), int(cd.right()), int(y))

        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.qimage:
            cd = self._to_display(self.crop_rect)
            if cd.contains(event.position()):
                self._dragging = True
                ip = self._to_image(event.position())
                self._drag_offset = QPointF(ip.x() - self.crop_rect.x(),
                                            ip.y() - self.crop_rect.y())
                self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._dragging and self.qimage:
            ip = self._to_image(event.position())
            iw, ih = self.qimage.width(), self.qimage.height()
            nx = max(0.0, min(ip.x() - self._drag_offset.x(),
                              iw - self.crop_rect.width()))
            ny = max(0.0, min(ip.y() - self._drag_offset.y(),
                              ih - self.crop_rect.height()))
            self.crop_rect.moveTopLeft(QPointF(nx, ny))
            self.update()
            self.crop_changed.emit()
        elif self.qimage:
            cd = self._to_display(self.crop_rect)
            if cd.contains(event.position()):
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            if self.qimage:
                cd = self._to_display(self.crop_rect)
                if cd.contains(event.position()):
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, event):
        if not self.qimage:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return

        factor = 0.94 if delta > 0 else 1.06
        cx, cy = self.crop_rect.center().x(), self.crop_rect.center().y()
        nw = self.crop_rect.width() * factor
        nh = self.crop_rect.height() * factor

        if nw < 60 or nh < 60:
            return

        mw, mh = self._max_crop_dims()
        nw = min(nw, mw)
        nh = min(nh, mh)
        # enforce ratio
        target = self.ratio_w / self.ratio_h
        nh = nw / target

        iw, ih = self.qimage.width(), self.qimage.height()
        nx = max(0.0, min(cx - nw / 2, iw - nw))
        ny = max(0.0, min(cy - nh / 2, ih - nh))

        self.crop_rect = QRectF(nx, ny, nw, nh)
        self.update()
        self.crop_changed.emit()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.photos = scan_photos(settings["input_dir"])
        self.idx = 0
        self.states: dict[int, dict] = {}   # saved crop states
        self.exported: set[int] = set()
        self.skipped: set[int] = set()

        self.original: Image.Image | None = None
        self.display_scale = 1.0
        self.rotation = 0

        self.setWindowTitle("Orezavanie fotiek pre tlac")
        self.setMinimumSize(960, 700)
        self._build_ui()
        self._bind_shortcuts()
        self.showMaximized()
        self._load_photo()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        cw = QWidget()
        self.setCentralWidget(cw)
        ml = QVBoxLayout(cw)
        ml.setContentsMargins(8, 8, 8, 8)
        ml.setSpacing(8)

        # Header
        hl = QHBoxLayout()
        self.counter_lbl = QLabel()
        f = self.counter_lbl.font()
        f.setPointSize(13)
        self.counter_lbl.setFont(f)
        self.file_lbl = QLabel()
        self.file_lbl.setStyleSheet("color: gray;")
        hl.addWidget(self.counter_lbl)
        hl.addStretch()
        hl.addWidget(self.file_lbl)
        ml.addLayout(hl)

        # Editor
        self.editor = CropEditor()
        self.editor.crop_changed.connect(self._sync_slider)
        ml.addWidget(self.editor, 1)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(10)

        self.rot_l_btn = QPushButton("Otocit vlavo")
        self.rot_l_btn.clicked.connect(lambda: self._rotate("left"))
        tb.addWidget(self.rot_l_btn)
        self.rot_r_btn = QPushButton("Otocit vpravo")
        self.rot_r_btn.clicked.connect(lambda: self._rotate("right"))
        tb.addWidget(self.rot_r_btn)

        tb.addStretch()

        tb.addWidget(QLabel("Velkost vyrezu:"))
        self.zoom_sl = QSlider(Qt.Orientation.Horizontal)
        self.zoom_sl.setRange(5, 100)
        self.zoom_sl.setValue(100)
        self.zoom_sl.setMaximumWidth(220)
        self.zoom_sl.setToolTip("Koliecko mysi na fotografii funguje tiez")
        self.zoom_sl.valueChanged.connect(self._on_zoom)
        tb.addWidget(self.zoom_sl)

        tb.addStretch()

        self.back_btn = QPushButton("Spat")
        self.back_btn.clicked.connect(self._go_back)
        tb.addWidget(self.back_btn)

        self.skip_btn = QPushButton("Preskocit  (S)")
        self.skip_btn.setMinimumWidth(140)
        self.skip_btn.setMinimumHeight(40)
        self.skip_btn.setToolTip(
            "Fotku neupravovat - nebude ulozena vo vystupnom priecinku")
        self.skip_btn.clicked.connect(self._skip)
        tb.addWidget(self.skip_btn)

        self.ok_btn = QPushButton("Potvrdit  (Enter)")
        self.ok_btn.setMinimumWidth(170)
        self.ok_btn.setMinimumHeight(40)
        bf = self.ok_btn.font()
        bf.setBold(True)
        self.ok_btn.setFont(bf)
        self.ok_btn.clicked.connect(self._confirm)
        tb.addWidget(self.ok_btn)

        ml.addLayout(tb)

        # Progress
        self.progress = QProgressBar()
        self.progress.setMaximum(len(self.photos))
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("Spracovane: %v z %m")
        ml.addWidget(self.progress)

    def _bind_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, self._confirm)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, self._confirm)
        QShortcut(QKeySequence(Qt.Key.Key_S), self, self._skip)

    # -- photo loading -------------------------------------------------------

    def _load_photo(self):
        if self.idx >= len(self.photos):
            self._finish()
            return

        path = self.photos[self.idx]
        self.counter_lbl.setText(f"Fotka {self.idx + 1} z {len(self.photos)}")
        self.file_lbl.setText(path.name)
        self.back_btn.setEnabled(self.idx > 0)

        try:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
        except Exception as exc:
            QMessageBox.warning(self, "Chyba",
                                f"Nepodarilo sa nacitat: {path.name}\n{exc}")
            self.idx += 1
            self._load_photo()
            return

        self.original = img

        state = self.states.get(self.idx)
        self.rotation = state["rotation"] if state else 0

        self._refresh_display()

        if state and state.get("crop"):
            self.editor.set_crop(state["crop"])

        self._sync_slider()

    def _refresh_display(self):
        img = self.original
        if self.rotation:
            img = img.rotate(-self.rotation, expand=True)

        w, h = img.size
        mx = max(w, h)
        if mx > MAX_DISPLAY_SIZE:
            self.display_scale = MAX_DISPLAY_SIZE / mx
            img = img.resize((int(w * self.display_scale),
                              int(h * self.display_scale)),
                             Image.LANCZOS)
        else:
            self.display_scale = 1.0

        qimg = pil_to_qimage(img)
        rw, rh = self.settings["ratio_w"], self.settings["ratio_h"]
        if self.settings["auto_orient"]:
            rw, rh = adjusted_ratio(rw, rh, img.width, img.height)
        self.editor.set_image(qimg, rw, rh)

    # -- rotation ------------------------------------------------------------

    def _rotate(self, direction: str):
        self.rotation = (self.rotation + (90 if direction == "right" else -90)) % 360
        self._refresh_display()
        self._sync_slider()

    # -- zoom slider ---------------------------------------------------------

    def _sync_slider(self):
        if not self.editor.qimage:
            return
        mw, _ = self.editor._max_crop_dims()
        frac = self.editor.crop_rect.width() / mw if mw else 1
        self.zoom_sl.blockSignals(True)
        self.zoom_sl.setValue(max(5, min(100, int(frac * 100))))
        self.zoom_sl.blockSignals(False)

    def _on_zoom(self, value: int):
        if not self.editor.qimage:
            return
        mw, mh = self.editor._max_crop_dims()
        frac = value / 100.0
        nw = mw * frac
        nh = mh * frac
        if nw < 60 or nh < 60:
            return

        iw, ih = self.editor.qimage.width(), self.editor.qimage.height()
        cx, cy = self.editor.crop_rect.center().x(), self.editor.crop_rect.center().y()
        nx = max(0.0, min(cx - nw / 2, iw - nw))
        ny = max(0.0, min(cy - nh / 2, ih - nh))
        self.editor.crop_rect = QRectF(nx, ny, nw, nh)
        self.editor.update()

    # -- navigation ----------------------------------------------------------

    def _save_state(self):
        self.states[self.idx] = {
            "rotation": self.rotation,
            "crop": QRectF(self.editor.crop_rect),
        }

    def _confirm(self):
        self._save_state()
        self._export()
        self.exported.add(self.idx)
        self.skipped.discard(self.idx)
        self._update_progress()
        self.idx += 1
        self._load_photo()

    def _skip(self):
        self._save_state()
        if self.idx in self.exported:
            self._remove_exported()
            self.exported.discard(self.idx)
        self.skipped.add(self.idx)
        self._update_progress()
        self.idx += 1
        self._load_photo()

    def _go_back(self):
        if self.idx <= 0:
            return
        self._save_state()
        self.idx -= 1
        self._load_photo()

    def _update_progress(self):
        self.progress.setValue(len(self.exported) + len(self.skipped))

    # -- export --------------------------------------------------------------

    def _export(self):
        path = self.photos[self.idx]
        s = self.settings

        img = self.original.copy()
        if self.rotation:
            img = img.rotate(-self.rotation, expand=True)

        cr = self.editor.crop_rect
        sf = 1.0 / self.display_scale
        left = max(0, int(cr.x() * sf))
        top = max(0, int(cr.y() * sf))
        right = min(img.width, int((cr.x() + cr.width()) * sf))
        bottom = min(img.height, int((cr.y() + cr.height()) * sf))
        img = img.crop((left, top, right, bottom))

        out = Path(s["output_dir"]) / path.name
        kw: dict = {"dpi": (s["dpi"], s["dpi"])}
        ext = path.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            kw["quality"] = s["quality"]
            kw["subsampling"] = 0
        elif ext == ".webp":
            kw["quality"] = s["quality"]

        try:
            img.save(str(out), **kw)
        except Exception as exc:
            QMessageBox.warning(self, "Chyba pri ukladani",
                                f"Nepodarilo sa ulozit: {path.name}\n{exc}")

    def _remove_exported(self):
        path = self.photos[self.idx]
        out = Path(self.settings["output_dir"]) / path.name
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass

    # -- finish / close ------------------------------------------------------

    def _finish(self):
        saved = len(self.exported)
        skipped = len(self.skipped)
        msg = (f"Vsetky fotky ({len(self.photos)}) boli spracovane.\n"
               f"Ulozene: {saved}    Preskocene: {skipped}\n\n"
               f"Vystupny priecinok:\n{self.settings['output_dir']}\n\n"
               "Chcete otvorit vystupny priecinok?")
        reply = QMessageBox.information(
            self, "Hotovo!", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            import subprocess
            if sys.platform == "darwin":
                subprocess.Popen(["open", self.settings["output_dir"]])
            elif sys.platform == "win32":
                os.startfile(self.settings["output_dir"])
            else:
                subprocess.Popen(["xdg-open", self.settings["output_dir"]])
        self.close()

    def closeEvent(self, event):
        remaining = len(self.photos) - len(self.exported) - len(self.skipped)
        if remaining > 0 and self.idx < len(self.photos):
            r = QMessageBox.question(
                self, "Ukoncit?",
                f"Zostava {remaining} nespracovanych fotiek.\n"
                "Naozaj chcete ukoncit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if r == QMessageBox.StandardButton.No:
                event.ignore()
                return
        event.accept()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Orezavanie fotiek pre tlac")

    dlg = SettingsDialog()
    if dlg.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)

    win = MainWindow(dlg.get_settings())
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
