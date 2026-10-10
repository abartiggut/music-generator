<#
.SYNOPSIS
Installiert die Windows-App mit eigener Python-3.12-Umgebung.
.DESCRIPTION
Standard: Mock mit Testklaengen, ohne KI-Modelle. -Mode Ssh -SshHost verbindet
einen eigenen GPU-Server, -Mode Remote -ServerUrl direkt, -Mode Local baut CUDA.
Bestehende Startkonfiguration bleibt ohne explizite Parameter erhalten.
.EXAMPLE
.\Install.ps1 -Mode Mock -NoStart -NoBrowser
.EXAMPLE
.\Install.ps1 -Mode Remote -ServerUrl http://gpu-server:18085 -NoStart
.EXAMPLE
.\Install.ps1 -Mode Local -LmSize 4B
#>
[CmdletBinding()]
param(
    [ValidateSet('Ssh', 'Remote', 'Mock', 'Local')][string]$Mode = 'Mock',
    [string]$ServerUrl,
    [ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9_.@-]*$')][string]$SshHost,
    [ValidateRange(1024, 65535)][int]$RemotePort = 18085,
    [ValidateRange(1024, 65535)][int]$TunnelPort = 18085,
    [ValidateRange(1024, 65535)][int]$Port = 8765,
    [ValidateSet('0.6B', '1.7B', '4B')][string]$LmSize = '4B',
    [switch]$NoStart,
    [switch]$NoBrowser
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
. (Join-Path $Root 'scripts\windows\common.ps1')
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Dieser Installer ist fuer Windows. Unter macOS Install.command verwenden.' }
    Set-Location -LiteralPath $Root
    $Data = Join-Path $Root 'data'
    New-Item -ItemType Directory -Path $Data -Force | Out-Null
    $ConfPath = Join-Path $Data 'launcher.json'
    $Config = @{}
    if (Test-Path -LiteralPath $ConfPath) {
        $Saved = Get-Content -LiteralPath $ConfPath -Raw | ConvertFrom-Json
        foreach ($Property in $Saved.PSObject.Properties) { $Config[$Property.Name] = $Property.Value }
    }
    $Defaults = @{ mode = 'mock'; server_url = ''; ssh_host = ''; remote_port = 18085; tunnel_port = 18085; port = 8765; no_browser = $false }
    foreach ($Key in $Defaults.Keys) { if (-not $Config.ContainsKey($Key)) { $Config[$Key] = $Defaults[$Key] } }
    if ($PSBoundParameters.ContainsKey('Mode')) {
        $Config.mode = switch ($Mode) { 'Mock' { 'mock' }; 'Local' { 'local' }; default { 'remote' } }
        if ($Mode -eq 'Remote') { $Config.ssh_host = '' }
        if ($Mode -eq 'Ssh') {
            if (-not $PSBoundParameters.ContainsKey('SshHost')) { throw '-Mode Ssh benoetigt -SshHost mit deinem eigenen SSH-Alias oder user@hostname.' }
            $Config.ssh_host = $SshHost; $Config.server_url = ''
        }
        if ($Mode -eq 'Local') { $Config.server_url = ''; $Config.ssh_host = '' }
    }
    foreach ($Entry in @{ServerUrl='server_url';SshHost='ssh_host';RemotePort='remote_port';TunnelPort='tunnel_port';Port='port';NoBrowser='no_browser'}.GetEnumerator()) {
        if ($PSBoundParameters.ContainsKey($Entry.Key)) {
            $Value = Get-Variable -Name $Entry.Key -ValueOnly
            if ($Entry.Key -eq 'NoBrowser') { $Value = [bool]$Value }
            $Config[$Entry.Value] = $Value
        }
    }
    # An explicit URL implies a direct server unless an SSH host was explicit too.
    if ($PSBoundParameters.ContainsKey('ServerUrl')) {
        if ($PSBoundParameters.ContainsKey('Mode') -and $Mode -in @('Mock','Local')) { throw '-ServerUrl gehoert zu -Mode Remote oder Ssh, nicht zu Mock/Local.' }
        $Config.mode = 'remote'
        if (-not $PSBoundParameters.ContainsKey('SshHost')) { $Config.ssh_host = '' }
    }
    if ($PSBoundParameters.ContainsKey('SshHost') -and -not $PSBoundParameters.ContainsKey('Mode')) { $Config.mode = 'remote' }
    if ($Config.mode -notin @('mock','remote','local')) { throw 'launcher.json: mode muss mock, remote oder local sein.' }
    foreach ($Key in @('port','remote_port','tunnel_port')) {
        $Number = $Config[$Key]
        if (($Number -isnot [int] -and $Number -isnot [long]) -or $Number -lt 1024 -or $Number -gt 65535) { throw ('launcher.json: {0} muss eine Ganzzahl zwischen 1024 und 65535 sein.' -f $Key) }
    }
    if ($Config.mode -ne 'mock' -and $Config.port -eq $Config.tunnel_port) { throw 'Web-Port und Modell-/Tunnel-Port muessen verschieden sein.' }
    if ($Config.ssh_host -and ([string]$Config.ssh_host -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_.@-]*$')) { throw 'launcher.json: ssh_host muss ein SSH-Alias oder user@hostname sein.' }
    if ($Config.no_browser -isnot [bool]) { throw 'launcher.json: no_browser muss true oder false sein.' }
    if ($Config.mode -eq 'remote' -and -not $Config.ssh_host) {
        $Uri = $null
        if (-not [Uri]::TryCreate([string]$Config.server_url, [UriKind]::Absolute, [ref]$Uri) -or $Uri.Scheme -notin @('http','https') -or -not $Uri.Host -or $Uri.UserInfo) {
            throw 'Remote benoetigt -ServerUrl http(s)://SERVER:PORT ohne Zugangsdaten.'
        }
    }
    $Git = Find-WindowsTool 'git.exe'
    if (-not $Git) { throw 'Git fehlt. Git for Windows installieren: https://git-scm.com/downloads/win' }
    Invoke-Checked $Git @('--version')
    $Uv = Find-WindowsTool 'uv.exe'
    if (-not $Uv) {
        Write-Host 'uv fehlt; installiere den offiziellen Benutzer-Installer (ohne Administratorrechte).'
        $UvInstaller = Join-Path $env:TEMP ('music-generator-uv-' + [guid]::NewGuid().ToString() + '.ps1')
        Invoke-WebRequest -UseBasicParsing -Uri 'https://astral.sh/uv/install.ps1' -OutFile $UvInstaller
        try { Invoke-Checked 'powershell.exe' @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$UvInstaller) }
        finally { Remove-Item -LiteralPath $UvInstaller -ErrorAction SilentlyContinue }
        $Uv = Find-WindowsTool 'uv.exe'
        if (-not $Uv) { throw 'uv wurde nicht gefunden. https://docs.astral.sh/uv/getting-started/installation/' }
    }
    Write-Host 'Installiere die Python-Pakete aus uv.lock (Python 3.12).'
    $Python = Join-Path $Root '.venv\Scripts\python.exe'
    if ((Test-Path -LiteralPath (Join-Path $Root '.venv')) -and -not (Test-Path -LiteralPath $Python)) {
        throw '.venv existiert bereits, ist aber keine Windows-Umgebung. Bitte separat sichern/umbenennen und erneut starten; sie wird nicht geloescht.'
    }
    if (Test-Path -LiteralPath $Python) {
        $Version = & $Python -c 'import sys; print(str(sys.version_info.major) + chr(46) + str(sys.version_info.minor))'
        if ($LASTEXITCODE -ne 0 -or $Version -ne '3.12') { throw 'Die vorhandene .venv verwendet nicht Python 3.12. Bitte separat sichern/umbenennen; sie wird nicht geloescht.' }
    }
    # Avoid a user's global uv environment override changing another project.
    $PreviousEnv = $env:UV_PROJECT_ENVIRONMENT
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $Root '.venv'
    try { Invoke-Checked $Uv @('sync','--frozen','--python','3.12','--project',$Root) }
    finally { $env:UV_PROJECT_ENVIRONMENT = $PreviousEnv }
    if ($Config.mode -eq 'local') {
        . (Join-Path $Root 'scripts\windows\local-engine.ps1')
        if (-not $PSBoundParameters.ContainsKey('LmSize') -and $Config.ContainsKey('lm_model') -and $Config.lm_model -match '^acestep-5Hz-lm-(0\.6B|1\.7B|4B)-Q8_0\.gguf$') { $LmSize = $Matches[1] }
        Install-LocalEngine -Root $Root -Git $Git -LmSize $LmSize -Config $Config
    } elseif ($Config.mode -eq 'remote' -and $Config.ssh_host) {
        $Ssh = Find-WindowsTool 'ssh.exe'
        if (-not $Ssh) { throw 'OpenSSH Client fehlt. Unter Windows: Einstellungen > Optionale Features > OpenSSH Client.' }
        Write-Host ('Pruefe vorhandenen SSH-Zugang zu {0} (keine Aenderungen am Server).' -f $Config.ssh_host)
        Invoke-Checked $Ssh @('-o','BatchMode=yes','-o','ConnectTimeout=10',[string]$Config.ssh_host,'true')
        Write-Host ('Der ace-server muss auf {0}:127.0.0.1:{1} laufen. Der Launcher richtet nur den SSH-Tunnel ein.' -f $Config.ssh_host,$Config.remote_port)
    }
    # Save only after installation succeeded, retain all unknown config properties.
    $TemporaryConfig = Join-Path $Data ('launcher-' + [guid]::NewGuid().ToString() + '.tmp')
    [IO.File]::WriteAllText($TemporaryConfig, ($Config | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $TemporaryConfig -Destination $ConfPath -Force
    Write-Host ('Bereit: {0}, Web-Port {1}.' -f $Config.mode,$Config.port)
    if (-not $NoStart) { Invoke-Checked $Python @('-m','app.launcher','start') }
    exit 0
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
