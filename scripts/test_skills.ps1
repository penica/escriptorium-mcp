$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('mcp skills test ' + [Guid]::NewGuid().ToString('N'))
$savedDestination = $env:ESCRIPTORIUM_SKILLS_DIR
$savedVersion = $env:ESCRIPTORIUM_RELEASE_VERSION
try {
    $env:ESCRIPTORIUM_SKILLS_DIR = Join-Path $testRoot 'client skills'
    $env:ESCRIPTORIUM_RELEASE_VERSION = '0.18.0'
    $script = Get-Content -LiteralPath (Join-Path $repoRoot 'install-skills.ps1') -Raw
    Invoke-Expression $script
    $target = Join-Path $env:ESCRIPTORIUM_SKILLS_DIR 'escriptorium'
    $skill = Join-Path $target 'SKILL.md'
    $expected = (Get-FileHash -LiteralPath $skill -Algorithm SHA256).Hash
    if (-not (Test-Path -LiteralPath (Join-Path $target 'docs/FONTS-API.md'))) { throw 'Missing bundled references.' }
    Write-Host 'PASS: first PowerShell install from real GitHub release'
    Invoke-Expression $script
    if (Test-Path -LiteralPath (Join-Path $testRoot 'skill-backups')) { throw 'No-op created a backup.' }
    Write-Host 'PASS: unchanged skill is a no-op'
    Add-Content -LiteralPath $skill -Value 'Local customization'
    $customized = (Get-FileHash -LiteralPath $skill -Algorithm SHA256).Hash
    Invoke-Expression $script
    $backups = @(Get-ChildItem -LiteralPath (Join-Path $testRoot 'skill-backups') -Recurse -Filter SKILL.md)
    if ($backups.Count -ne 1 -or (Get-FileHash -LiteralPath $backups[0].FullName -Algorithm SHA256).Hash -ne $customized) { throw 'Previous skill not preserved.' }
    if ((Get-FileHash -LiteralPath $skill -Algorithm SHA256).Hash -ne $expected) { throw 'Published skill not restored.' }
    Write-Host 'PASS: update backs up local modifications'
    $env:ESCRIPTORIUM_RELEASE_VERSION = 'invalid/version'
    $failed = $false
    try { Invoke-Expression $script } catch { $failed = $true }
    if (-not $failed -or (Get-FileHash -LiteralPath $skill -Algorithm SHA256).Hash -ne $expected) { throw 'Invalid version changed the existing skill.' }
    Write-Host 'PASS: failed install retains existing skill'
    $env:ESCRIPTORIUM_RELEASE_VERSION = '0.18.0'
    $lock = Join-Path $testRoot '.escriptorium-skill-install.lock'
    [IO.File]::WriteAllText($lock, 'fixture lock')
    $failed = $false
    try { Invoke-Expression $script } catch { $failed = $true }
    if (-not $failed -or -not (Test-Path -LiteralPath $lock)) { throw 'Concurrent install not refused.' }
    Remove-Item -LiteralPath $lock
    Write-Host 'PASS: concurrent install refused without removing another lock'
}
finally {
    $env:ESCRIPTORIUM_SKILLS_DIR = $savedDestination
    $env:ESCRIPTORIUM_RELEASE_VERSION = $savedVersion
    if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }
}
