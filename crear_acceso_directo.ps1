# crear_acceso_directo.ps1
# Crea un acceso directo de ¡Quac! en el Escritorio, apuntando al .exe compilado.
# Ejecutar: clic derecho > "Ejecutar con PowerShell"

$nombre     = "Quac"
$carpeta    = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe        = Join-Path $carpeta "dist\Quac\Quac.exe"
$escritorio = [Environment]::GetFolderPath("Desktop")
$destino    = Join-Path $escritorio "$nombre.lnk"

if (-not (Test-Path $exe)) {
    Write-Host "No se encontró el ejecutable en: $exe" -ForegroundColor Red
    Write-Host "Compila primero con: python -m PyInstaller quac.spec --clean"
    exit 1
}

$wsh  = New-Object -ComObject WScript.Shell
$link = $wsh.CreateShortcut($destino)
$link.TargetPath       = $exe
$link.WorkingDirectory = Split-Path -Parent $exe
$link.Description      = "Quac - Analisis de prensa electoral colombiana"
$link.IconLocation     = $exe
$link.Save()

Write-Host "Acceso directo creado en: $destino" -ForegroundColor Green
