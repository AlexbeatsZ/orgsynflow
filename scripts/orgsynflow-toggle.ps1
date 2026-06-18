param(
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WebRoot = Join-Path $ProjectRoot "web"
$TempRoot = Join-Path $env:LOCALAPPDATA "Temp\codex\orgsynflow"
$StatePath = Join-Path $TempRoot "orgsynflow-toggle-state.json"
$ApiLog = Join-Path $TempRoot "api.log"
$WebLog = Join-Path $TempRoot "web.log"
$ApiPort = 8765
$WebPort = 5173
$Url = "http://127.0.0.1:$WebPort/"

New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

function ConvertTo-SingleQuotedLiteral {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Get-AliveProcess {
    param([int]$ProcessId)
    if ($ProcessId -le 0) {
        return $null
    }
    return Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
}

function Get-PortOwnerProcess {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction SilentlyContinue
        if (-not $process) {
            continue
        }
        $commandLine = [string]$process.CommandLine
        if (
            $commandLine.Contains($ProjectRoot) -or
            $commandLine.Contains("run_api.py") -or
            $commandLine.Contains("vite") -or
            $commandLine.Contains("uvicorn")
        ) {
            [pscustomobject]@{
                Id = [int]$process.ProcessId
                CommandLine = $commandLine
            }
        }
    }
}

function Read-State {
    if (-not (Test-Path $StatePath)) {
        return $null
    }
    try {
        return Get-Content -Raw -Path $StatePath | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Get-StateInt {
    param(
        [object]$State,
        [string]$Name
    )
    if (-not $State) {
        return 0
    }
    $property = $State.PSObject.Properties[$Name]
    if (-not $property -or $null -eq $property.Value) {
        return 0
    }
    return [int]$property.Value
}

function Test-OrgSynFlowRunning {
    $state = Read-State
    if ($state) {
        if (Get-AliveProcess (Get-StateInt $state "api_pid")) {
            return $true
        }
        if (Get-AliveProcess (Get-StateInt $state "web_pid")) {
            return $true
        }
    }
    if (Get-PortOwnerProcess $ApiPort) {
        return $true
    }
    if (Get-PortOwnerProcess $WebPort) {
        return $true
    }
    return $false
}

function Stop-OrgSynFlow {
    Write-Host "Stopping OrgSynFlow..."
    $ids = New-Object System.Collections.Generic.HashSet[int]
    $state = Read-State
    if ($state) {
        [void]$ids.Add((Get-StateInt $state "api_pid"))
        [void]$ids.Add((Get-StateInt $state "web_pid"))
    }
    foreach ($owner in @(Get-PortOwnerProcess $ApiPort) + @(Get-PortOwnerProcess $WebPort)) {
        [void]$ids.Add([int]$owner.Id)
    }

    foreach ($processId in $ids) {
        if ($processId -le 0) {
            continue
        }
        $process = Get-AliveProcess $processId
        if ($process) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped PID $processId"
        }
    }

    Remove-Item -Path $StatePath -Force -ErrorAction SilentlyContinue
    Write-Host "OrgSynFlow stopped."
}

function Start-HiddenPowerShell {
    param(
        [string]$WorkingDirectory,
        [string]$Command,
        [string]$LogPath
    )
    $quotedWorkingDirectory = ConvertTo-SingleQuotedLiteral $WorkingDirectory
    $quotedLogPath = ConvertTo-SingleQuotedLiteral $LogPath
    $script = "Set-Location -LiteralPath $quotedWorkingDirectory; $Command *> $quotedLogPath"
    return Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -PassThru -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $script
    )
}

function Wait-ForPort {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 45
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Start-OrgSynFlow {
    Write-Host "Starting OrgSynFlow..."
    if (-not (Test-Path (Join-Path $ProjectRoot "run_api.py"))) {
        throw "Cannot find run_api.py under $ProjectRoot"
    }
    if (-not (Test-Path (Join-Path $WebRoot "package.json"))) {
        throw "Cannot find web/package.json under $ProjectRoot"
    }

    $apiProcess = Start-HiddenPowerShell -WorkingDirectory $ProjectRoot -Command "uv run python run_api.py" -LogPath $ApiLog
    $webProcess = Start-HiddenPowerShell -WorkingDirectory $WebRoot -Command "npm run dev" -LogPath $WebLog

    @{
        api_pid = $apiProcess.Id
        web_pid = $webProcess.Id
        api_port = $ApiPort
        web_port = $WebPort
        url = $Url
        started_at = (Get-Date).ToString("o")
        api_log = $ApiLog
        web_log = $WebLog
    } | ConvertTo-Json | Set-Content -Encoding UTF8 -Path $StatePath

    $apiReady = Wait-ForPort $ApiPort
    $webReady = Wait-ForPort $WebPort

    if (-not $apiReady -or -not $webReady) {
        Write-Host "Startup did not fully finish within timeout."
        Write-Host "API ready: $apiReady; Web ready: $webReady"
        Write-Host "Logs:"
        Write-Host "  $ApiLog"
        Write-Host "  $WebLog"
        exit 2
    }

    Write-Host "OrgSynFlow is running:"
    Write-Host "  $Url"
    Write-Host "Logs:"
    Write-Host "  $ApiLog"
    Write-Host "  $WebLog"

    if (-not $NoOpen) {
        Start-Process $Url
    }
}

if (Test-OrgSynFlowRunning) {
    Stop-OrgSynFlow
}
else {
    Start-OrgSynFlow
}
