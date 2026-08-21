import os
import sys
import shutil
import subprocess

# Garante compatibilidade do pipeline VTK e layout de teclado no X11/WSLg
if sys.platform.startswith("linux"):
    os.environ.setdefault("VTK_DISABLE_SHM", "1")
    try:
        if shutil.which("setxkbmap"):
            subprocess.run(["setxkbmap", "-model", "abnt2", "-layout", "br"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _ensure_openfoam_env():
    """Detecta e carrega automaticamente as variáveis de ambiente do OpenFOAM se não estiverem presentes."""
    if shutil.which("blockMesh"):
        return
    
    import glob
    candidates = [
        "/opt/openfoam12/etc/bashrc",
        "/opt/openfoam11/etc/bashrc",
        "/opt/openfoam10/etc/bashrc",
        "/opt/openfoam9/etc/bashrc",
        "/usr/lib/openfoam/openfoam2406/etc/bashrc",
        "/usr/lib/openfoam/openfoam2312/etc/bashrc",
        "/usr/lib/openfoam/openfoam2212/etc/bashrc",
    ]
    candidates.extend(glob.glob("/opt/openfoam*/etc/bashrc"))
    candidates.extend(glob.glob("/usr/lib/openfoam*/etc/bashrc"))
    candidates.extend(glob.glob("/usr/lib/openfoam/openfoam*/etc/bashrc"))
    candidates.extend(glob.glob(os.path.expanduser("~/OpenFOAM/OpenFOAM-*/etc/bashrc")))
    
    target_rc = None
    for rc in candidates:
        if os.path.isfile(rc):
            target_rc = rc
            break
            
    if target_rc:
        try:
            cmd = f"source {target_rc} && env"
            res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, check=False)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if "=" in line:
                        k, _, v = line.partition("=")
                        if k in [
                            "PATH", "LD_LIBRARY_PATH", "WM_PROJECT_DIR", "WM_PROJECT", 
                            "WM_PROJECT_VERSION", "FOAM_APP", "FOAM_SRC", "FOAM_LIBBIN", 
                            "FOAM_APPBIN", "FOAM_USER_APPBIN", "FOAM_USER_LIBBIN", 
                            "FOAM_RUN", "FOAM_TUTORIALS", "WM_OPTIONS", "WM_COMPILER",
                            "WM_ARCH", "WM_PRECISION_OPTION"
                        ]:
                            os.environ[k] = v
        except Exception:
            pass


_ensure_openfoam_env()

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from gafoam.main_window import MainWindow
from gafoam.resources import load_application_fonts


def run(argv=None):
    """Sobe a interface e devolve o código de saída do loop de eventos."""
    app = QApplication(argv if argv is not None else sys.argv)
    try:
        app.setAttribute(Qt.AA_DontShowIconsInMenus, False)
    except Exception:
        pass
    load_application_fonts()

    # Define Inter como a fonte padrão de toda a aplicação
    default_font = QFont("Inter", 10)
    default_font.setStyleHint(QFont.SansSerif)
    app.setFont(default_font)

    window = MainWindow()
    window.show()
    return app.exec()

