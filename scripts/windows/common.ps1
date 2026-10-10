# Native Windows helpers shared by Install.ps1 and the optional CUDA installation.
function Find-WindowsTool {
    param([string]$Name)
    $Command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Command) { return $Command.Source }
    if ($Name -eq 'uv.exe') {
        foreach ($Candidate in @((Join-Path $env:USERPROFILE '.local\bin\uv.exe'), (Join-Path $env:USERPROFILE '.cargo\bin\uv.exe'))) {
            if (Test-Path -LiteralPath $Candidate) { return $Candidate }
        }
    }
    return $null
}
function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('{0} fehlgeschlagen (Exit-Code {1}).' -f (Split-Path $Executable -Leaf),$LASTEXITCODE) }
}
