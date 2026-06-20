param(
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WebRoot = Join-Path $ProjectRoot "web"
$DefaultChemformerRoot = Join-Path (Split-Path -Parent $ProjectRoot) "chem-ai\work-4"
$ChemformerRoot = if ($env:CHEMFORMER_ROOT) { $env:CHEMFORMER_ROOT } else { $DefaultChemformerRoot }
$ChemformerUrl = if ($env:CHEMFORMER_URL) { $env:CHEMFORMER_URL.TrimEnd("/") } else { "http://127.0.0.1:8000" }
$ChemformerUri = [uri]$ChemformerUrl
$ChemformerIsLocal = $ChemformerUri.Host -in @("127.0.0.1", "localhost", "::1")
$ChemformerPort = if ($ChemformerUri.IsDefaultPort) { 80 } else { $ChemformerUri.Port }
$TempRoot = Join-Path $env:LOCALAPPDATA "Temp\.agents\orgsynflow"
$StatePath = Join-Path $TempRoot "orgsynflow-toggle-state.json"
$ApiLog = Join-Path $TempRoot "api.log"
$WebLog = Join-Path $TempRoot "web.log"
$ChemformerLog = Join-Path $TempRoot "chemformer.log"
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

function Get-PortProcess {
    param([int]$Port)
    foreach ($connection in @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction SilentlyContinue
        if ($process) {
            [pscustomobject]@{
                Id = [int]$process.ProcessId
                CommandLine = [string]$process.CommandLine
            }
        }
    }
}

function Test-ProcessRole {
    param(
        [object]$Process,
        [ValidateSet("api", "web", "chemformer")][string]$Role
    )
    if (-not $Process) {
        return $false
    }
    $commandLine = [string]$Process.CommandLine
    if ($Role -eq "api") {
        return $commandLine.Contains("run_api.py")
    }
    if ($Role -eq "web") {
        return $commandLine.Contains($WebRoot) -and $commandLine.Contains("vite")
    }
    return $commandLine.Contains("webapp.backend.app:app")
}

function Get-RolePortProcesses {
    param(
        [int]$Port,
        [ValidateSet("api", "web", "chemformer")][string]$Role
    )
    return @(Get-PortProcess $Port | Where-Object { Test-ProcessRole $_ $Role })
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
    param([object]$State, [string]$Name)
    if (-not $State) {
        return 0
    }
    $property = $State.PSObject.Properties[$Name]
    if (-not $property -or $null -eq $property.Value) {
        return 0
    }
    return [int]$property.Value
}

function Get-StateBool {
    param([object]$State, [string]$Name)
    if (-not $State) {
        return $false
    }
    $property = $State.PSObject.Properties[$Name]
    return [bool]($property -and $property.Value)
}

function Test-OrgSynFlowRunning {
    $state = Read-State
    if ($state) {
        if (Get-AliveProcess (Get-StateInt $state "api_pid")) { return $true }
        if (Get-AliveProcess (Get-StateInt $state "web_pid")) { return $true }
    }
    if (Get-RolePortProcesses $ApiPort "api") { return $true }
    if (Get-RolePortProcesses $WebPort "web") { return $true }
    return $false
}

function Stop-OrgSynFlow {
    Write-Host "Stopping OrgSynFlow..."
    $ids = New-Object System.Collections.Generic.HashSet[int]
    $state = Read-State
    if ($state) {
        [void]$ids.Add((Get-StateInt $state "api_pid"))
        [void]$ids.Add((Get-StateInt $state "web_pid"))
        if (Get-StateBool $state "chemformer_managed") {
            [void]$ids.Add((Get-StateInt $state "chemformer_pid"))
        }
    }
    foreach ($owner in @(Get-RolePortProcesses $ApiPort "api") + @(Get-RolePortProcesses $WebPort "web")) {
        [void]$ids.Add([int]$owner.Id)
    }
    if (Get-StateBool $state "chemformer_managed") {
        foreach ($owner in @(Get-RolePortProcesses $ChemformerPort "chemformer")) {
            [void]$ids.Add([int]$owner.Id)
        }
    }

    foreach ($processId in $ids) {
        if ($processId -le 0) { continue }
        if (Get-AliveProcess $processId) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped PID $processId"
        }
    }
    Remove-Item -Path $StatePath -Force -ErrorAction SilentlyContinue
    Write-Host "OrgSynFlow stopped."
}

function Start-HiddenPowerShell {
    param([string]$WorkingDirectory, [string]$Command, [string]$LogPath)
    $quotedWorkingDirectory = ConvertTo-SingleQuotedLiteral $WorkingDirectory
    $quotedLogPath = ConvertTo-SingleQuotedLiteral $LogPath
    $script = "Set-Location -LiteralPath $quotedWorkingDirectory; $Command *> $quotedLogPath"
    return Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -PassThru -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $script
    )
}

function Wait-ForPort {
    param([int]$Port, [int]$TimeoutSeconds = 45)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Wait-ForHttp {
    param([string]$HealthUrl, [int]$TimeoutSeconds = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 3
            if ($response.status -eq "ok") { return $true }
        }
        catch {}
        Start-Sleep -Milliseconds 750
    }
    return $false
}

function Assert-ChemformerAssets {
    if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
        throw "Cannot find conda required by the Chemformer sidecar."
    }
    $requiredPaths = @(
        (Join-Path $ChemformerRoot "webapp\backend\app.py"),
        (Join-Path $ChemformerRoot "models\fine_tune_compatible.ckpt"),
        (Join-Path $ChemformerRoot "models\bart_vocab_downstream.json")
    )
    foreach ($path in $requiredPaths) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Chemformer asset not found: $path"
        }
    }
    conda run -n aizynthmodels python -c "import aizynthmodels, torch" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Conda environment 'aizynthmodels' is unavailable or incomplete."
    }
}

function Start-OrgSynFlow {
    Write-Host "Starting OrgSynFlow..."
    if (-not (Test-Path (Join-Path $ProjectRoot "run_api.py"))) { throw "Cannot find run_api.py under $ProjectRoot" }
    if (-not (Test-Path (Join-Path $WebRoot "package.json"))) { throw "Cannot find web/package.json under $ProjectRoot" }

    $chemformerProcess = $null
    $chemformerManaged = $false
    if ($ChemformerIsLocal) {
        $portProcesses = @(Get-PortProcess $ChemformerPort)
        if ($portProcesses.Count -eq 0) {
            Assert-ChemformerAssets
            $chemformerProcess = Start-HiddenPowerShell `
                -WorkingDirectory $ChemformerRoot `
                -Command "conda run -n aizynthmodels python -m uvicorn webapp.backend.app:app --host 127.0.0.1 --port $ChemformerPort" `
                -LogPath $ChemformerLog
            $chemformerManaged = $true
        }
    }

    $apiProcess = Start-HiddenPowerShell -WorkingDirectory $ProjectRoot -Command "uv run python run_api.py" -LogPath $ApiLog
    $webProcess = Start-HiddenPowerShell -WorkingDirectory $WebRoot -Command "npm run dev" -LogPath $WebLog

    @{
        api_pid = $apiProcess.Id
        web_pid = $webProcess.Id
        chemformer_pid = if ($chemformerProcess) { $chemformerProcess.Id } else { 0 }
        chemformer_managed = $chemformerManaged
        api_port = $ApiPort
        web_port = $WebPort
        chemformer_url = $ChemformerUrl
        url = $Url
        started_at = (Get-Date).ToString("o")
        api_log = $ApiLog
        web_log = $WebLog
        chemformer_log = $ChemformerLog
    } | ConvertTo-Json | Set-Content -Encoding UTF8 -Path $StatePath

    $chemformerReady = Wait-ForHttp "$ChemformerUrl/api/health"
    $apiReady = Wait-ForPort $ApiPort
    $webReady = Wait-ForPort $WebPort
    if (-not $chemformerReady -or -not $apiReady -or -not $webReady) {
        Write-Host "Startup did not fully finish within timeout."
        Write-Host "Chemformer ready: $chemformerReady; API ready: $apiReady; Web ready: $webReady"
        Write-Host "Logs: $ChemformerLog, $ApiLog, $WebLog"
        exit 2
    }

    Write-Host "OrgSynFlow is running: $Url"
    Write-Host "Chemformer: $ChemformerUrl"
    Write-Host "Logs: $TempRoot"
    if (-not $NoOpen) { Start-Process $Url }
}

if (Test-OrgSynFlowRunning) {
    Stop-OrgSynFlow
}
else {
    Start-OrgSynFlow
}
