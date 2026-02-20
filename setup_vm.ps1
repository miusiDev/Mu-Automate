# =============================================================================
# setup_vm.ps1 — Instala todo lo necesario para correr MU Automate en una VM
# Ejecutar como Administrador:
#   Set-ExecutionPolicy Bypass -Scope Process -Force; .\setup_vm.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

# --- Configuracion -----------------------------------------------------------
$PYTHON_VERSION   = "3.13.2"
$PYTHON_URL       = "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-amd64.exe"
$TESSERACT_URL    = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe"
$GIT_URL          = "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.2/Git-2.47.1.2-64-bit.exe"
$DXRUNTIME_URL    = "https://download.microsoft.com/download/1/7/1/1718CCC4-6315-4D8E-9543-8E28A4E18C4C/dxwebsetup.exe"
$VCREDIST_URL     = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
$INSTALL_DIR      = "E:\MuAutomate"
$TESSERACT_DIR    = "C:\Tesseract-OCR"
$REPO_URL         = "https://github.com/miusiDev/Mu-Automate.git"

$DOWNLOADS        = "$env:TEMP\mu_automate_setup"

# --- Helpers -----------------------------------------------------------------
function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Download-File($url, $dest) {
    if (Test-Path $dest) { Write-Host "  Ya existe: $dest" ; return }
    Write-Host "  Descargando $url ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $maxRetries = 3
    for ($i = 1; $i -le $maxRetries; $i++) {
        try {
            $wc = New-Object System.Net.WebClient
            $wc.DownloadFile($url, $dest)
            Write-Host "  Descarga OK."
            return
        } catch {
            Write-Host "  Intento $i/$maxRetries fallo: $_" -ForegroundColor Yellow
            if ($i -eq $maxRetries) { throw "No se pudo descargar $url despues de $maxRetries intentos." }
            Start-Sleep -Seconds 5
        }
    }
}

New-Item -ItemType Directory -Path $DOWNLOADS -Force | Out-Null

# =============================================================================
# 1. Dependencias del juego (DirectX 9, Visual C++)
# =============================================================================
Write-Step "Instalando DirectX 9.0c End-User Runtime"
$dxExe = "$DOWNLOADS\dxwebsetup.exe"
Download-File $DXRUNTIME_URL $dxExe
Start-Process -FilePath $dxExe -ArgumentList "/Q" -Wait -NoNewWindow
Write-Host "  DirectX instalado."

Write-Step "Instalando Visual C++ Redistributable 2015-2022"
$vcExe = "$DOWNLOADS\vc_redist.x64.exe"
Download-File $VCREDIST_URL $vcExe
Start-Process -FilePath $vcExe -ArgumentList "/install", "/quiet", "/norestart" -Wait -NoNewWindow
Write-Host "  Visual C++ Redistributable instalado."

# =============================================================================
# 2. Python
# =============================================================================
Write-Step "Instalando Python $PYTHON_VERSION"
$pythonExe = "$DOWNLOADS\python-installer.exe"
Download-File $PYTHON_URL $pythonExe

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $pythonExe -ArgumentList `
        "/quiet", "InstallAllUsers=1", "PrependPath=1", `
        "Include_pip=1", "Include_tcltk=0" `
        -Wait -NoNewWindow
    # Refrescar PATH en la sesion actual
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")
    Write-Host "  Python instalado."
} else {
    Write-Host "  Python ya esta instalado: $(python --version)"
}

# =============================================================================
# 3. Git
# =============================================================================
Write-Step "Instalando Git"
$gitExe = "$DOWNLOADS\git-installer.exe"
Download-File $GIT_URL $gitExe

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $gitExe -ArgumentList "/VERYSILENT", "/NORESTART" -Wait -NoNewWindow
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")
    Write-Host "  Git instalado."
} else {
    Write-Host "  Git ya esta instalado: $(git --version)"
}

# =============================================================================
# 4. Tesseract OCR
# =============================================================================
Write-Step "Instalando Tesseract OCR en $TESSERACT_DIR"
$tessExe = "$DOWNLOADS\tesseract-installer.exe"
Download-File $TESSERACT_URL $tessExe

if (-not (Test-Path "$TESSERACT_DIR\tesseract.exe")) {
    Start-Process -FilePath $tessExe -ArgumentList "/S", "/D=$TESSERACT_DIR" -Wait -NoNewWindow
    Write-Host "  Tesseract instalado en $TESSERACT_DIR"
} else {
    Write-Host "  Tesseract ya esta instalado."
}

# =============================================================================
# 5. Clonar repositorio
# =============================================================================
Write-Step "Clonando repositorio en $INSTALL_DIR"
if (-not (Test-Path "$INSTALL_DIR\.git")) {
    git clone $REPO_URL $INSTALL_DIR
} else {
    Write-Host "  Repo ya existe, haciendo pull..."
    Push-Location $INSTALL_DIR
    git pull
    Pop-Location
}

# =============================================================================
# 6. Virtual environment + dependencias
# =============================================================================
Write-Step "Creando virtual environment"
Push-Location $INSTALL_DIR

python -m venv .venv
& .\.venv\Scripts\Activate.ps1

Write-Step "Instalando dependencias Python"
python -m pip install --upgrade pip
pip install -r requirements.txt

# pywin32 necesita un post-install
python -m pywin32_postinstall -install 2>$null

Write-Step "Verificando instalacion"
python -c "
import pyautogui, pydirectinput, pyperclip, pytesseract
import cv2, numpy, win32gui, yaml, colorlog
print('Todas las dependencias OK')
"

Pop-Location

# =============================================================================
# 7. Recordatorios finales
# =============================================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " INSTALACION COMPLETA" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Cosas que debes ajustar manualmente:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. Editar config.yaml (o servers/heroesmu.yaml):"
Write-Host "     - tesseract_path: '$TESSERACT_DIR/tesseract.exe'"
Write-Host "     - launcher.exe_path: ruta al .exe del juego"
Write-Host "     - launcher.login_steps[3].text: tu password"
Write-Host "     - Coordenadas de botones (dependen de la resolucion)"
Write-Host ""
Write-Host "  2. Resolucion de pantalla: usar la misma que en la maquina original"
Write-Host "     o recalibrar con: python tools\calibrate_launcher.py"
Write-Host ""
Write-Host "  3. Para correr:" -ForegroundColor Cyan
Write-Host "     cd $INSTALL_DIR"
Write-Host "     .\.venv\Scripts\Activate.ps1"
Write-Host "     python run.py"
Write-Host ""
