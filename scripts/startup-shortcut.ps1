param(
    [switch]$Install,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "Road2Maniacs Discord Webhooks.lnk"

if ($Install -eq $Uninstall) {
    throw "Choose either -Install or -Uninstall."
}

if ($Install) {
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = Join-Path $ProjectRoot "start.cmd"
    $Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description = "Start Road2Maniacs Discord Webhooks in a visible window"
    $Shortcut.Save()
    Write-Host "Installed the startup shortcut. The bot will open visibly after Windows sign-in."
}
else {
    if (Test-Path -LiteralPath $ShortcutPath) {
        Remove-Item -LiteralPath $ShortcutPath
        Write-Host "Removed the startup shortcut."
    }
    else {
        Write-Host "No startup shortcut was installed."
    }
}

