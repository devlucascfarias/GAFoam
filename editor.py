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
    """Destacador de sintaxe completo e otimizado para arquivos OpenFOAM e blocos C++ embutidos."""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 1. Formatos de Texto
        
        # Comentários
        self.commentFormat = QTextCharFormat()
        self.commentFormat.setForeground(QColor(106, 115, 125)) # Cinza-verde (estilo GitHub)
        self.commentFormat.setFontItalic(True)
        
        # Delimitadores de código C++ #{ e #}
        self.cppDelimiterFormat = QTextCharFormat()
        self.cppDelimiterFormat.setForeground(QColor(215, 58, 73)) # Vermelho
        self.cppDelimiterFormat.setFontWeight(QFont.Bold)
        
        # Strings
        self.stringFormat = QTextCharFormat()
        self.stringFormat.setForeground(QColor(3, 47, 98)) # Azul escuro/marinho
        
        # Números
        self.numberFormat = QTextCharFormat()
        self.numberFormat.setForeground(QColor(0, 92, 197)) # Azul claro/médio
        
        # Diretivas do OpenFOAM (#include, #inputMode, etc.)
        self.directiveFormat = QTextCharFormat()
        self.directiveFormat.setForeground(QColor(227, 98, 9)) # Laranja/Marrom
        self.directiveFormat.setFontWeight(QFont.Bold)
        
        # Variáveis e macros ($variável)
        self.macroFormat = QTextCharFormat()
        self.macroFormat.setForeground(QColor(215, 58, 73)) # Vermelho
        self.macroFormat.setFontWeight(QFont.Bold)
        
        # Cabeçalho FoamFile
        self.foamFileFormat = QTextCharFormat()
        self.foamFileFormat.setForeground(QColor(111, 66, 193)) # Roxo
        self.foamFileFormat.setFontWeight(QFont.Bold)
        
        # Palavras-chave do OpenFOAM (controlDict, fvSchemes, fvSolution, etc.)
        self.keywordFormat = QTextCharFormat()
        self.keywordFormat.setForeground(QColor(3, 102, 214)) # Azul
        self.keywordFormat.setFontWeight(QFont.Bold)
        
        # Valores pré-definidos (uniform, nonuniform, ascii, binary, yes, no, true, false, on, off)
        self.valueFormat = QTextCharFormat()
        self.valueFormat.setForeground(QColor(227, 98, 9)) # Laranja
        self.valueFormat.setFontWeight(QFont.Medium)
        
        # Tipos comuns e condições de contorno (fixedValue, zeroGradient, etc.)
        self.typeFormat = QTextCharFormat()
        self.typeFormat.setForeground(QColor(0, 134, 179)) # Azul-esverdeado
        self.typeFormat.setFontWeight(QFont.Medium)
        
        # Formatos C++
        self.cppKeywordFormat = QTextCharFormat()
        self.cppKeywordFormat.setForeground(QColor(111, 66, 193)) # Roxo
        self.cppKeywordFormat.setFontWeight(QFont.Bold)
        
        self.cppTypeFormat = QTextCharFormat()
        self.cppTypeFormat.setForeground(QColor(0, 134, 179)) # Azul-esverdeado
        self.cppTypeFormat.setFontWeight(QFont.Medium)
        
        self.cppFunctionFormat = QTextCharFormat()
        self.cppFunctionFormat.setForeground(QColor(3, 102, 214)) # Azul
        
        # 2. Definição das Regras e Expressões Regulares
        
        # Regras Comuns (Strings e Números)
        self.commonRules = [
            (QRegularExpression(r'"(?:[^"\\]|\\.)*"'), self.stringFormat),
            (QRegularExpression(r"'(?:[^'\\]|\\.)*'"), self.stringFormat),
            (QRegularExpression(r"\b-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\b"), self.numberFormat)
        ]
        
        # Regras OpenFOAM
        self.foamRules = [
            # Diretivas
            (QRegularExpression(r"#(?:include|includeIfPresent|inputMode|includeEtc|merge|remove)\b"), self.directiveFormat),
            # Macros e referências de variáveis
            (QRegularExpression(r"\$\w+"), self.macroFormat),
            # FoamFile keywords
            (QRegularExpression(r"\b(?:FoamFile|format|class|location|object)\b"), self.foamFileFormat),
            # Palavras-chave de dicionários
            (QRegularExpression(r"\b(?:dimensions|internalField|boundaryField|application|solver|startFrom|startTime|stopAt|endTime|deltaT|writeControl|writeInterval|purgeWrite|writeFormat|writePrecision|writeCompression|timeFormat|timePrecision|runTimeModifiable|adjustTimeStep|maxCo|maxAlphaCo|maxDeltaT|type|libs|solvers|relaxationFactors|fields|equations|nNonOrthogonalCorrectors|nCorrectors|nOuterCorrectors|tolerance|relTol|smoother|preconditioner)\b"), self.keywordFormat),
            # Valores pré-definidos
            (QRegularExpression(r"\b(?:uniform|nonuniform|ascii|binary|yes|no|true|false|on|off)\b"), self.valueFormat),
            # Tipos de condições de contorno e solvers
            (QRegularExpression(r"\b(?:fixedValue|fixedGradient|calculated|zeroGradient|empty|symmetry|symmetryPlane|patch|wall|noSlip|inletOutlet|slip|codedFixedValue|totalPressure|pressureInletOutletVelocity|GAMG|smoothSolver|DICGaussSeidel|symGaussSeidel|PIMPLE|PISO|SIMPLE)\b"), self.typeFormat)
        ]
        
        # Regras C++
        self.cppRules = [
            # Palavras-chave C++
            (QRegularExpression(r"\b(?:const|double|float|int|bool|if|else|for|while|return|static|class|this|virtual|void|public|private|protected|new|delete|switch|case|break|continue)\b"), self.cppKeywordFormat),
            # Tipos e classes C++/OpenFOAM
            (QRegularExpression(r"\b(?:scalar|vector|tensor|label|vectorField|scalarField|fvPatch|Info|endl|symmTensor|point|bool|string|word)\b"), self.cppTypeFormat),
            # Funções e macros matemáticas do OpenFOAM
            (QRegularExpression(r"\b(?:forAll|gSum|mag|sqrt|exp|sqr|max|min|fmod|sin|cos|tan|log|pow|Info|Warning|FatalError|endl)\b"), self.cppFunctionFormat)
        ]

    def getComplementRanges(self, length, excluded_ranges):
        if not excluded_ranges:
            return [(0, length)]
        sorted_ranges = sorted(excluded_ranges, key=lambda x: x[0])
        complement = []
        last_end = 0
        for start, end in sorted_ranges:
            if start > last_end:
                complement.append((last_end, start))
            last_end = max(last_end, end)
        if last_end < length:
            complement.append((last_end, length))
        return complement

    def applyRule(self, text, pattern, format, target_ranges):
        it = pattern.globalMatch(text)
        while it.hasNext():
            m = it.next()
            start = m.capturedStart()
            length = m.capturedLength()
            for r_start, r_end in target_ranges:
                if start >= r_start and (start + length) <= r_end:
                    self.setFormat(start, length, format)
                    break

    def highlightBlock(self, text):
        prevState = self.previousBlockState()
        if prevState < 0:
            prevState = 0
            
        cpp_ranges = []
        comment_ranges = []
        cpp_delimiters = []
        
        current_state = prevState
        idx = 0
        length = len(text)
        block_start = 0
        comment_start = 0
        
        while idx < length:
            if current_state == 0: # Estado OpenFOAM
                if idx + 1 < length and text[idx] == '/' and text[idx+1] == '*':
                    comment_start = idx
                    current_state = 1
                    idx += 2
                elif idx + 1 < length and text[idx] == '/' and text[idx+1] == '/':
                    comment_ranges.append((idx, length))
                    break
                elif idx + 1 < length and text[idx] == '#' and text[idx+1] == '{':
                    cpp_delimiters.append((idx, idx + 2))
                    current_state = 2
                    idx += 2
                    block_start = idx
                elif text[idx] in ('"', "'"):
                    quote = text[idx]
                    idx += 1
                    while idx < length:
                        if text[idx] == '\\' and idx + 1 < length:
                            idx += 2
                        elif text[idx] == quote:
                            idx += 1
                            break
                        else:
                            idx += 1
                else:
                    idx += 1
                    
            elif current_state == 1: # Estado Comentário Multilinha
                if idx + 1 < length and text[idx] == '*' and text[idx+1] == '/':
                    comment_ranges.append((comment_start, idx + 2))
                    current_state = 0
                    idx += 2
                else:
                    idx += 1
                    
            elif current_state == 2: # Estado Bloco C++
                if idx + 1 < length and text[idx] == '#' and text[idx+1] == '}':
                    cpp_ranges.append((block_start, idx))
                    cpp_delimiters.append((idx, idx + 2))
                    current_state = 0
                    idx += 2
                elif idx + 1 < length and text[idx] == '/' and text[idx+1] == '/':
                    cpp_end_idx = text.find('#}', idx)
                    if cpp_end_idx != -1:
                        comment_ranges.append((idx, cpp_end_idx))
                        cpp_ranges.append((block_start, idx))
                        cpp_delimiters.append((cpp_end_idx, cpp_end_idx + 2))
                        current_state = 0
                        idx = cpp_end_idx + 2
                    else:
                        comment_ranges.append((idx, length))
                        cpp_ranges.append((block_start, idx))
                        break
                elif idx + 1 < length and text[idx] == '/' and text[idx+1] == '*':
                    cpp_end_idx = text.find('#}', idx)
                    comment_end_idx = text.find('*/', idx)
                    if comment_end_idx != -1 and (cpp_end_idx == -1 or comment_end_idx < cpp_end_idx):
                        comment_ranges.append((idx, comment_end_idx + 2))
                        cpp_ranges.append((block_start, idx))
                        idx = comment_end_idx + 2
                        block_start = idx
                    else:
                        if cpp_end_idx != -1:
                            comment_ranges.append((idx, cpp_end_idx))
                            cpp_ranges.append((block_start, idx))
                            cpp_delimiters.append((cpp_end_idx, cpp_end_idx + 2))
                            current_state = 0
                            idx = cpp_end_idx + 2
                        else:
                            comment_ranges.append((idx, length))
                            cpp_ranges.append((block_start, idx))
                            current_state = 1
                            break
                elif text[idx] in ('"', "'"):
                    quote = text[idx]
                    idx += 1
                    while idx < length:
                        if text[idx] == '\\' and idx + 1 < length:
                            idx += 2
                        elif text[idx] == quote:
                            idx += 1
                            break
                        else:
                            idx += 1
                else:
                    idx += 1
                    
        if current_state == 1 and prevState != 1:
            comment_ranges.append((comment_start, length))
        elif current_state == 1 and prevState == 1:
            comment_ranges.append((0, length))
        elif current_state == 2:
            cpp_ranges.append((block_start, length))
            
        self.setCurrentBlockState(current_state)
        
        # Calcular as regiões onde a sintaxe OpenFOAM deve ser aplicada
        excluded = comment_ranges + cpp_ranges + cpp_delimiters
        foam_ranges = self.getComplementRanges(length, excluded)
        
        # Aplicar regras OpenFOAM nas regiões de dicionário
        for pattern, fmt in self.foamRules:
            self.applyRule(text, pattern, fmt, foam_ranges)
            
        # Aplicar regras C++ nas regiões de código C++
        for pattern, fmt in self.cppRules:
            self.applyRule(text, pattern, fmt, cpp_ranges)
            
        # Aplicar regras comuns (strings e números) nas regiões normais e de código C++
        common_targets = foam_ranges + cpp_ranges
        for pattern, fmt in self.commonRules:
            self.applyRule(text, pattern, fmt, common_targets)
            
        # Aplicar formato de comentário (sobrescrevendo qualquer outra regra nessas posições)
        for start, end in comment_ranges:
            self.setFormat(start, end - start, self.commentFormat)
            
        # Aplicar formato de delimitador C++
        for start, end in cpp_delimiters:
            self.setFormat(start, end - start, self.cppDelimiterFormat)
