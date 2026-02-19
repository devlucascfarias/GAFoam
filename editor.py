from PySide6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit
from PySide6.QtGui import QTextCharFormat, QPainter, QColor, QFont, QSyntaxHighlighter
from PySide6.QtCore import QSize, QRect, Qt, QRegularExpression


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

        class LineNumberArea(QWidget):
            def __init__(self, editor):
                super().__init__(editor)
                self._editor = editor

            def sizeHint(self):
                return QSize(self._editor.lineNumberAreaWidth(), 0)

            def paintEvent(self, event):
                self._editor.lineNumberAreaPaintEvent(event)

        self.lineNumberArea = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateLineNumberAreaWidth(0)

    def lineNumberAreaWidth(self):
        digits = 1
        max_block = max(1, self.blockCount())
        while max_block >= 10:
            max_block //= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def highlightCurrentLine(self):
        extraSelections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor(232, 242, 255)
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextCharFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)
        self.setExtraSelections(extraSelections)

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor(245, 245, 245))
        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        fm = self.fontMetrics()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.setPen(QColor(120, 120, 120))
                painter.drawText(0, top, self.lineNumberArea.width() - 3, fm.height(), Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1

    def wheelEvent(self, event):
        super().wheelEvent(event)


class SimpleHighlighter(QSyntaxHighlighter):
    """Sintaxe simples para arquivos OpenFOAM/dicionários.

    Recebe um `QTextDocument` como parent (por exemplo, `editor.document()`).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        kw_format = QTextCharFormat()
        kw_format.setForeground(QColor(0, 0, 150))
        kw_format.setFontWeight(QFont.Bold)
        keywords = [r"\bFoamFile\b", r"\bversion\b", r"\bformat\b", r"\bclass\b", r"\blocation\b"]
        for kw in keywords:
            self.rules.append((QRegularExpression(kw), kw_format))

        num_format = QTextCharFormat()
        num_format.setForeground(QColor(150, 0, 0))
        self.rules.append((QRegularExpression(r"\b\d+\.?\d*\b"), num_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(0, 128, 0))
        self.rules.append((QRegularExpression(r"//.*"), comment_format))
        self.rules.append((QRegularExpression(r"/\*.*?\*/"), comment_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)
