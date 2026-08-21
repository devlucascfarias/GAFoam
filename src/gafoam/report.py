"""PDF report generator for OpenFOAM simulation results."""

import os
from PySide6.QtGui import QPdfWriter, QPainter, QFont, QColor, QPageLayout, QPageSize
from PySide6.QtCore import QMarginsF, QRectF, QDateTime, Qt

from gafoam import foamdict

class ReportGenerator:
    """Generates PDF reports for OpenFOAM simulations."""
    
    def __init__(self, case_path: str, chart_pixmap=None, convergence_data: dict = None, sim_info: dict = None):
        """
        Initialize the report generator.
        
        Args:
            case_path: Path to the OpenFOAM case directory.
            chart_pixmap: QPixmap of the residuals chart (can be None).
            convergence_data: Dictionary mapping variable name -> last residual value.
            sim_info: Dictionary with keys: solver, endTime, deltaT, iterations, sim_time.
        """
        self.case_path = case_path
        self.chart_pixmap = chart_pixmap
        self.convergence_data = convergence_data or {}
        self.sim_info = sim_info or {}
        
        # Carbon Design System colors
        self.color_primary = QColor("#0f62fe")
        self.color_text = QColor("#161616")
        self.color_text_secondary = QColor("#525252")
        self.color_border = QColor("#e0e0e0")
        
        self.y_pos = 0.0
        self.page_height = 0.0
        self.page_width = 0.0
        self.painter = None
        self.writer = None

    def generate_pdf(self, output_path: str) -> bool:
        """
        Generate the PDF report.
        
        Args:
            output_path: Path where the PDF will be saved.
            
        Returns:
            bool: True on success, False on error.
        """
        try:
            self.writer = QPdfWriter(output_path)
            
            # Setup page layout
            layout = QPageLayout()
            layout.setPageSize(QPageSize(QPageSize.A4))
            layout.setOrientation(QPageLayout.Portrait)
            layout.setMargins(QMarginsF(20, 20, 20, 20)) # 20mm margins
            self.writer.setPageLayout(layout)
            self.writer.setResolution(300) # 300 DPI
            
            self.painter = QPainter()
            if not self.painter.begin(self.writer):
                return False
                
            self.page_width = self.writer.width()
            self.page_height = self.writer.height()
            self.y_pos = 0
            
            # 1. Header
            self._draw_header()
            
            # 2. Case Parameters
            self._draw_section_title("Case Parameters")
            self._draw_case_parameters()
            
            # 3. Residuals Chart
            if self.chart_pixmap:
                self._check_page_break(self.page_width * 0.5) # estimate chart height
                self._draw_section_title("Residuals Chart")
                self._draw_chart()
                
            # 4. Convergence Summary
            self._check_page_break(1500)
            self._draw_section_title("Convergence Summary")
            self._draw_convergence_summary()
            
            # 5. Simulation Statistics
            self._check_page_break(1000)
            self._draw_section_title("Simulation Statistics")
            self._draw_simulation_statistics()
            
            # 6. Footer (drawn at the end for the last page)
            self._draw_footer()
            
            self.painter.end()
            return True
            
        except Exception as e:
            print(f"Error generating PDF report: {e}")
            if self.painter and self.painter.isActive():
                self.painter.end()
            return False

    def _check_page_break(self, required_height: float):
        """Check if we need a new page and add one if necessary."""
        if self.y_pos + required_height > self.page_height:
            self._draw_footer()
            self.writer.newPage()
            self.y_pos = 0

    def _draw_header(self):
        """Draw the report header."""
        font_title = QFont("Inter", 22, QFont.Bold)
        self.painter.setFont(font_title)
        self.painter.setPen(self.color_text)
        
        title = "GAFoam — Simulation Report"
        self.painter.drawText(0, int(self.y_pos), int(self.page_width), 1000, Qt.AlignLeft | Qt.AlignTop, title)
        
        self.y_pos += 1200
        
        font_subtitle = QFont("Inter", 12)
        self.painter.setFont(font_subtitle)
        self.painter.setPen(self.color_text_secondary)
        
        date_str = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        case_name = os.path.basename(os.path.normpath(self.case_path))
        
        subtitle = f"Date: {date_str} | Case: {case_name}"
        self.painter.drawText(0, int(self.y_pos), int(self.page_width), 600, Qt.AlignLeft | Qt.AlignTop, subtitle)
        
        self.y_pos += 800
        
        # Draw line separator
        self.painter.setPen(self.color_border)
        self.painter.drawLine(0, int(self.y_pos), int(self.page_width), int(self.y_pos))
        self.y_pos += 400

    def _draw_section_title(self, title: str):
        """Draw a section title."""
        self.y_pos += 400
        font = QFont("Inter", 16, QFont.Bold)
        self.painter.setFont(font)
        self.painter.setPen(self.color_primary)
        
        self.painter.drawText(0, int(self.y_pos), int(self.page_width), 800, Qt.AlignLeft | Qt.AlignTop, title)
        self.y_pos += 1000

    def _draw_table(self, headers: list, data: list):
        """Draw a table with the given headers and data."""
        if not data:
            return
            
        cols = len(headers)
        if cols == 0:
            return
            
        col_width = self.page_width / cols
        row_height = 600
        
        # Headers
        font_bold = QFont("Inter", 10, QFont.Bold)
        self.painter.setFont(font_bold)
        self.painter.setPen(self.color_text)
        
        for i, header in enumerate(headers):
            rect = QRectF(i * col_width, self.y_pos, col_width, row_height)
            self.painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, f"  {header}")
            
        self.y_pos += row_height
        
        # Grid line under header
        self.painter.setPen(self.color_border)
        self.painter.drawLine(0, int(self.y_pos), int(self.page_width), int(self.y_pos))
        
        # Data
        font_regular = QFont("Inter", 10)
        self.painter.setFont(font_regular)
        self.painter.setPen(self.color_text)
        
        for row in data:
            self._check_page_break(row_height)
            for i, item in enumerate(row):
                rect = QRectF(i * col_width, self.y_pos, col_width, row_height)
                self.painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, f"  {str(item)}")
            self.y_pos += row_height
            
            # Row grid line
            self.painter.setPen(self.color_border)
            self.painter.drawLine(0, int(self.y_pos), int(self.page_width), int(self.y_pos))

        self.y_pos += 400

    def _draw_case_parameters(self):
        """Draw the case parameters section reading from controlDict."""
        try:
            ctrl_dict = foamdict.read_control_dict(self.case_path)
            
            params = [
                "application", "startFrom", "endTime", 
                "deltaT", "writeControl", "writeInterval"
            ]
            
            data = []
            for p in params:
                val = ctrl_dict.get(p, "N/A")
                data.append([p, val])
                
            self._draw_table(["Parameter", "Value"], data)
        except Exception as e:
            font = QFont("Inter", 10)
            self.painter.setFont(font)
            self.painter.setPen(self.color_text)
            self.painter.drawText(0, int(self.y_pos), int(self.page_width), 600, Qt.AlignLeft | Qt.AlignTop, f"Error reading case parameters: {e}")
            self.y_pos += 800

    def _draw_chart(self):
        """Draw the residuals chart."""
        if not self.chart_pixmap or self.chart_pixmap.isNull():
            return
            
        # Scale to fit width while maintaining aspect ratio
        target_width = self.page_width
        ratio = self.chart_pixmap.height() / self.chart_pixmap.width()
        target_height = target_width * ratio
        
        self._check_page_break(target_height + 400)
        
        rect = QRectF(0, self.y_pos, target_width, target_height)
        self.painter.drawPixmap(rect, self.chart_pixmap, QRectF(self.chart_pixmap.rect()))
        
        self.y_pos += target_height + 400

    def _draw_convergence_summary(self):
        """Draw the convergence summary section."""
        try:
            targets = foamdict.parse_residual_controls(self.case_path)
        except Exception:
            targets = {}
            
        data = []
        for var, final_val in self.convergence_data.items():
            try:
                val_float = float(final_val)
            except (ValueError, TypeError):
                val_float = None

            if val_float is not None:
                target = foamdict.match_residual_target(targets, var, 1e-5)
                is_co = "co" in var.lower() or "courant" in var.lower()
                if is_co and val_float > 1.0:
                    status = "Warning"
                elif val_float <= target:
                    status = "Converged"
                else:
                    status = "Iterating"
                val_str = f"{val_float:.2e}"
            else:
                status = "Unknown"
                val_str = str(final_val)

            data.append([var, val_str, status])

            
        if not data:
            data.append(["N/A", "N/A", "N/A"])
            
        self._draw_table(["Variable", "Final Value", "Status"], data)

    def _draw_simulation_statistics(self):
        """Draw the simulation statistics section."""
        stats = [
            ["Solver", self.sim_info.get("solver", "N/A")],
            ["Total Iterations", self.sim_info.get("iterations", "N/A")],
            ["Final Simulation Time", self.sim_info.get("sim_time", "N/A")],
            ["End Time (target)", self.sim_info.get("endTime", "N/A")],
            ["Delta T", self.sim_info.get("deltaT", "N/A")]
        ]
        
        self._draw_table(["Statistic", "Value"], stats)

    def _draw_footer(self):
        """Draw the page footer."""
        font = QFont("Inter", 8)
        self.painter.setFont(font)
        self.painter.setPen(self.color_text_secondary)

        
        footer_text = f"Generated by GAFoam | {QDateTime.currentDateTime().toString(Qt.ISODate)}"
        
        # Draw at the bottom of the page
        footer_y = self.page_height - 400
        
        self.painter.drawText(0, int(footer_y), int(self.page_width), 400, Qt.AlignCenter | Qt.AlignBottom, footer_text)
