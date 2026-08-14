$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$Requirements = Join-Path $ProjectRoot "requirements.txt"
$EnvFile = Join-Path $ProjectRoot ".env"
$EnvExample = Join-Path $ProjectRoot ".env.example"

Write-Host "Preparing Road2Maniacs Discord Webhooks..."

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
    if ($Python) {
        & $Python.Source -3 -m venv $VenvPath
    }
    else {
        $Python = Get-Command python -ErrorAction Stop
        & $Python.Source -m venv $VenvPath
    }
}

& $VenvPython -m pip install --disable-pip-version-check -r $Requirements

if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Write-Host "Created .env. Add the Discord webhook URL before publishing."
}
else {
    Write-Host "Kept the existing .env configuration."
}

Write-Host "Setup complete. Run preview.cmd first, then start.cmd."

