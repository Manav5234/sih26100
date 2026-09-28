<#
.SYNOPSIS
  Start the backend API on http://localhost:8010 from a fresh terminal.

.DESCRIPTION
  Runs from any PowerShell window with zero manual env setup:
    - cd's to backend/ (this script lives in backend/scripts/)
    - frees port 8010 if something is already listening on it
    - runs uvicorn in the foreground; Ctrl+C stops it
  Settings come from backend/.env via app/config.py.

  Run it yourself:  .\backend\scripts\dev_up.ps1
#>

$ErrorActionPreference = 'Stop'

# Always run from backend/, wherever this script was invoked from.
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

# Free port 8010 (a leftover uvicorn, a zombie, or another app).
$listening = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    foreach ($procId in ($listening | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $procName = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host ("freed port 8010: pid {0} ({1})" -f $procId, $procName)
    }
    Start-Sleep -Milliseconds 500
}

Write-Host ("starting uvicorn on http://localhost:8010 from {0}" -f (Get-Location))
python -m uvicorn app.main:app --port 8010
