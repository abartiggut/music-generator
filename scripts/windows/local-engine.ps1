# Explicit CUDA installation. No silent CPU fallback or system-tool installation.
function Install-LocalEngine {
    param([string]$Root, [string]$Git, [string]$LmSize, [hashtable]$Config)
    $Engine = Join-Path $Root 'engine\acestep.cpp'
    $Build = Join-Path $Engine 'build-cuda'
    $Models = Join-Path $Engine 'models'
    $Data = Join-Path $Root 'data'
    $Revision = 'b7ba6d9ce2f19ca7627fb8f340032c3ebe8ae253'
    $VsWhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path -LiteralPath $VsWhere)) { throw 'Visual C++ Build Tools 2022 fehlen: https://visualstudio.microsoft.com/visual-cpp-build-tools/ (Desktop development with C++).' }
    $VsPath = & $VsWhere -latest -products '*' -version '[17.0,18.0)' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $VsPath) { throw 'Visual Studio 2022 mit Desktop development with C++ fehlt. Bitte Build Tools installieren und erneut starten.' }
    $Nvcc = Find-WindowsTool 'nvcc.exe'
    if (-not $Nvcc -and $env:CUDA_PATH) {
        $Candidate = Join-Path $env:CUDA_PATH 'bin\nvcc.exe'
        if (Test-Path -LiteralPath $Candidate) { $Nvcc = $Candidate }
    }
    if (-not $Nvcc) { throw 'CUDA Toolkit fehlt (der NVIDIA-Treiber alleine reicht nicht). https://developer.nvidia.com/cuda-downloads ; fuer Blackwell mindestens CUDA 12.8.' }
    $NvccVersion = (& $Nvcc --version) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw 'nvcc konnte nicht gestartet werden.' }
    Write-Host $NvccVersion
    if ($NvccVersion -match 'release ([0-9]+)\.([0-9]+)' -and [version]($Matches[1] + '.' + $Matches[2]) -lt [version]'12.8') {
        throw 'Dieser CUDA-Installer benoetigt Toolkit 12.8 oder neuer (inklusive Blackwell-Unterstuetzung).'
    }
    $NvidiaSmi = Find-WindowsTool 'nvidia-smi.exe'
    if (-not $NvidiaSmi) { throw 'NVIDIA-Treiber/GPU nicht gefunden. Local benoetigt eine NVIDIA-CUDA-GPU; alternativ -Mode Ssh -SshHost GPU-SERVER oder -Mode Mock.' }
    Invoke-Checked $NvidiaSmi @('--query-gpu=name,memory.total','--format=csv,noheader')
    $Cmake = Find-WindowsTool 'cmake.exe'
    if (-not $Cmake) {
        $Candidate = Join-Path $VsPath 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
        if (Test-Path -LiteralPath $Candidate) { $Cmake = $Candidate }
    }
    if (-not $Cmake) { throw 'CMake fehlt. In Visual Studio Installer C++ CMake tools for Windows aktivieren oder https://cmake.org/download/ installieren.' }
    $CmakeVersion = (& $Cmake --version) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $CmakeVersion -notmatch 'cmake version ([0-9]+\.[0-9]+\.[0-9]+)') { throw 'CMake-Version konnte nicht geprueft werden.' }
    if ([version]$Matches[1] -lt [version]'3.24.0') { throw 'CMake ab 3.24 benoetigt (CUDA architecture native). Bitte CMake aktualisieren: https://cmake.org/download/' }
    $Curl = Find-WindowsTool 'curl.exe'
    if (-not $Curl) { throw 'curl.exe fehlt; benoetigt fuer wiederaufnehmbare Modell-Downloads.' }
    $ManifestPath = Join-Path $Root 'scripts\models.json'
    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    $LmFile = 'acestep-5Hz-lm-' + $LmSize + '-Q8_0.gguf'
    $Names = @('vae-BF16.gguf','Qwen3-Embedding-0.6B-Q8_0.gguf','acestep-v15-sft-Q8_0.gguf',$LmFile)
    $Files = @($Manifest.files | Where-Object { $_.name -in $Names })
    if ($Files.Count -ne 4) { throw 'scripts/models.json enthaelt nicht alle vier ausgewaehlten Modelle.' }
    foreach ($File in $Files) {
        if ($File.name -notmatch '^[a-zA-Z0-9_.-]+\.gguf$' -or $File.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or [long]$File.size -le 0) { throw 'Ungueltiger Modell-Manifest-Eintrag.' }
    }
    $DownloadBytes = [long]0
    foreach ($File in $Files) {
        $Target = Join-Path $Models $File.name
        if (-not (Test-Path -LiteralPath $Target)) {
            $DownloadBytes += [long]$File.size
            $Partial = $Target + '.part'
            if (Test-Path -LiteralPath $Partial) { $DownloadBytes -= [Math]::Min((Get-Item -LiteralPath $Partial).Length,[long]$File.size) }
        }
    }
    $Disk = (Get-Item -LiteralPath $Root).PSDrive
    if ($Disk.Free -and $Disk.Free -lt ($DownloadBytes + 3GB)) { throw ('Zu wenig freier Speicher: mindestens {0:N1} GB fuer Modelle und Build benoetigt.' -f (($DownloadBytes + 3GB) / 1GB)) }
    Write-Host ('CUDA-Engine {0}; Modell-Download etwa {1:N1} GB, Sprachmodell {2}.' -f $Revision,($DownloadBytes / 1GB),$LmSize)
    if (-not (Test-Path -LiteralPath (Join-Path $Engine '.git'))) {
        if (Test-Path -LiteralPath $Engine) {
            $Contents = @(Get-ChildItem -LiteralPath $Engine -Force | Where-Object { $_.Name -ne 'models' })
            if ($Contents.Count) { throw 'engine/acestep.cpp existiert ohne Git-Repository. Bitte separat sichern; der Installer ueberschreibt es nicht.' }
            # Git cannot clone into a nonempty models directory. Keep it in place and initialize.
            Invoke-Checked $Git @('-C',$Engine,'init')
            Invoke-Checked $Git @('-C',$Engine,'remote','add','origin','https://github.com/ServeurpersoCom/acestep.cpp.git')
            Invoke-Checked $Git @('-C',$Engine,'fetch','origin')
        } else { Invoke-Checked $Git @('clone','https://github.com/ServeurpersoCom/acestep.cpp.git',$Engine) }
    }
    $Origin = & $Git -C $Engine remote get-url origin
    if ($LASTEXITCODE -ne 0 -or $Origin -notmatch '^(https://github\.com/|git@github\.com:)ServeurpersoCom/acestep\.cpp(?:\.git)?/?$') {
        throw 'Die vorhandene Engine hat einen unerwarteten origin. Erwartet wird github.com/ServeurpersoCom/acestep.cpp; keine Aenderung am Repository vorgenommen.'
    }
    $Dirty = & $Git -C $Engine status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $Dirty) { throw 'Die Engine hat lokale Aenderungen. Bitte sichern/committen; ein automatischer Checkout wuerde sie veraendern.' }
    & $Git -C $Engine cat-file -e ($Revision + '^{commit}') 2>$null
    if ($LASTEXITCODE -ne 0) { Invoke-Checked $Git @('-C',$Engine,'fetch','origin') }
    Invoke-Checked $Git @('-C',$Engine,'checkout','--detach',$Revision)
    Invoke-Checked $Git @('-C',$Engine,'submodule','update','--init','--recursive')
    New-Item -ItemType Directory -Path $Models -Force | Out-Null
    $OldPath = $env:PATH
    $env:PATH = (Split-Path $Nvcc) + ';' + $env:PATH
    try {
        $BuildLog = Join-Path $Data 'build.log'
        Write-Host 'Baue ace-server mit CUDA (Log: data/build.log).'
        & $Cmake -S $Engine -B $Build -G 'Visual Studio 17 2022' -A x64 '-DGGML_CUDA=ON' '-DCMAKE_CUDA_ARCHITECTURES=native' 2>&1 | Out-File -LiteralPath $BuildLog -Encoding utf8
        if ($LASTEXITCODE -ne 0) { throw 'CUDA-Konfiguration fehlgeschlagen; siehe data/build.log. Kein CPU-Fallback.' }
        & $Cmake --build $Build --config Release --target ace-server --parallel 2>&1 | Out-File -LiteralPath $BuildLog -Append -Encoding utf8
        if ($LASTEXITCODE -ne 0) { throw 'CUDA-Build fehlgeschlagen; siehe data/build.log.' }
    } finally { $env:PATH = $OldPath }
    $Binary = Join-Path $Build 'Release\ace-server.exe'
    if (-not (Test-Path -LiteralPath $Binary)) { throw 'CUDA-Build lieferte keine Release/ace-server.exe.' }
    foreach ($File in $Files) {
        $Target = Join-Path $Models $File.name
        if (Test-Path -LiteralPath $Target) {
            Write-Host ('Pruefe SHA256: {0}' -f $File.name)
            if ((Get-Item -LiteralPath $Target).Length -ne [long]$File.size -or (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -ne $File.sha256) {
                throw ('Vorhandenes Modell {0} stimmt nicht mit dem Manifest ueberein. Bitte separat sichern/umbenennen und erneut starten.' -f $File.name)
            }
            continue
        }
        $Partial = $Target + '.part'
        if ((Test-Path -LiteralPath $Partial) -and (Get-Item -LiteralPath $Partial).Length -gt [long]$File.size) { throw ('Teil-Download {0} ist zu gross. Bitte separat umbenennen.' -f $Partial) }
        $Url = 'https://huggingface.co/' + $Manifest.repo + '/resolve/' + $Manifest.revision + '/' + $File.name
        Write-Host ('Lade {0}; erneuter Aufruf setzt einen Teil-Download fort.' -f $File.name)
        if (-not (Test-Path -LiteralPath $Partial) -or (Get-Item -LiteralPath $Partial).Length -lt [long]$File.size) {
            Invoke-Checked $Curl @('--location','--fail','--retry','3','--connect-timeout','30','--continue-at','-','--output',$Partial,$Url)
        }
        if ((Get-Item -LiteralPath $Partial).Length -ne [long]$File.size -or (Get-FileHash -LiteralPath $Partial -Algorithm SHA256).Hash -ne $File.sha256) {
            throw ('SHA256-Pruefung fuer {0} fehlgeschlagen. Teil-Download bleibt fuer Diagnose erhalten; bitte separat umbenennen, bevor erneut geladen wird.' -f $File.name)
        }
        Move-Item -LiteralPath $Partial -Destination $Target
    }
    $Config.local_engine = $Binary
    $Config.local_models = $Models
    $Config.lm_model = $LmFile
    $Config.cuda_bin = Split-Path $Nvcc -Parent
}
