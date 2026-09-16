function Install-EscriptoriumSkill {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    Set-StrictMode -Version Latest
    $skillsRoot = $env:ESCRIPTORIUM_SKILLS_DIR
    if (-not $skillsRoot) {
        $skillsRoot = Join-Path $HOME '.agents/skills'
        $codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
        $legacyRoot = Join-Path $codexRoot 'skills'
        if (Test-Path -LiteralPath (Join-Path $legacyRoot 'escriptorium')) {
            if (Test-Path -LiteralPath (Join-Path $skillsRoot 'escriptorium')) {
                throw 'Two eScriptorium skills exist. Set ESCRIPTORIUM_SKILLS_DIR to the one you want to update.'
            }
            $skillsRoot = $legacyRoot
        }
    }
    if (-not [IO.Path]::IsPathRooted($skillsRoot)) { throw 'ESCRIPTORIUM_SKILLS_DIR must be absolute.' }
    $skillsRoot = [IO.Path]::GetFullPath($skillsRoot)
    $target = Join-Path $skillsRoot 'escriptorium'
    if (Test-Path -LiteralPath $target) {
        $item = Get-Item -LiteralPath $target -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'The existing skill must be a real directory, not a file or link. Specify its real parent with ESCRIPTORIUM_SKILLS_DIR.'
        }
    }
    $null = New-Item -ItemType Directory -Path $skillsRoot -Force
    $parent = Split-Path -Parent $skillsRoot
    $lockPath = Join-Path $parent '.escriptorium-skill-install.lock'
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $work = Join-Path $parent ('.escriptorium-skill-stage.' + [Guid]::NewGuid().ToString('N'))
    $backup = $null
    try {
        $null = New-Item -ItemType Directory -Path $work
        $version = $env:ESCRIPTORIUM_RELEASE_VERSION
        if (-not $version) {
            $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/penica/escriptorium-mcp/releases/latest' -Headers @{ 'User-Agent' = 'escriptorium-skill-installer' } -TimeoutSec 120
            $version = $release.tag_name -replace '^v', ''
        }
        if ($version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { throw 'Expected a stable release version such as 1.1.0.' }
        $archive = "escriptorium-mcp-$version-wsl.tar.gz"
        $archivePath = Join-Path $work $archive
        $assetUrl = "https://github.com/penica/escriptorium-mcp/releases/download/v$version"
        Invoke-WebRequest -UseBasicParsing -Uri "$assetUrl/$archive" -OutFile $archivePath -TimeoutSec 300
        Invoke-WebRequest -UseBasicParsing -Uri "$assetUrl/$archive.sha256" -OutFile "$archivePath.sha256" -TimeoutSec 120
        $checksum = (Get-Content -LiteralPath "$archivePath.sha256" -Raw).Trim() -split '\s+'
        if ($checksum.Count -ne 2 -or $checksum[0] -notmatch '^[a-fA-F0-9]{64}$' -or $checksum[1] -cne $archive) {
            throw 'Invalid release checksum file.'
        }
        if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $checksum[0]) { throw 'Release checksum mismatch; existing skill unchanged.' }
        & tar -xzf $archivePath -C $work
        if ($LASTEXITCODE -ne 0) { throw 'Cannot extract the release archive; tar is required.' }
        $bundle = Join-Path $work "escriptorium-mcp-$version-wsl"
        foreach ($line in Get-Content -LiteralPath (Join-Path $bundle 'SHA256SUMS')) {
            if ($line -notmatch '^([a-fA-F0-9]{64})  (.+)$') { throw 'Invalid internal checksum record.' }
            $expected = $Matches[1]
            $relative = $Matches[2]
            if ($relative -match '(^|[/\\])\.\.([/\\]|$)' -or [IO.Path]::IsPathRooted($relative)) { throw 'Invalid internal checksum path.' }
            $file = Join-Path $bundle $relative
            if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $expected) { throw "Internal checksum mismatch: $relative" }
        }
        $source = Join-Path $bundle 'skills/escriptorium'
        if (-not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md') -PathType Leaf)) { throw 'The release contains no eScriptorium skill.' }
        Copy-Item -LiteralPath (Join-Path $bundle 'docs') -Destination (Join-Path $source 'docs') -Recurse
        [IO.File]::WriteAllText((Join-Path $source '.escriptorium-release'), "$version`n", [Text.UTF8Encoding]::new($false))
        function Get-SkillFiles([string]$Directory) {
            Get-ChildItem -LiteralPath $Directory -Recurse -File -Force | ForEach-Object {
                $_.FullName.Substring($Directory.Length) + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            } | Sort-Object
        }
        if (Test-Path -LiteralPath $target) {
            $sourceFiles = [string]::Join("`n", @(Get-SkillFiles $source))
            $targetFiles = [string]::Join("`n", @(Get-SkillFiles $target))
            if ($sourceFiles -ceq $targetFiles) {
                Write-Host "Skill already matches release $version at $target"
                return
            }
            $backupRoot = Join-Path $parent 'skill-backups'
            $null = New-Item -ItemType Directory -Path $backupRoot -Force
            $backup = Join-Path $backupRoot ('escriptorium.' + [Guid]::NewGuid().ToString('N'))
            Move-Item -LiteralPath $target -Destination $backup
        }
        Move-Item -LiteralPath $source -Destination $target
        if ($backup) { Write-Host "Previous skill backed up to $backup" }
        Write-Host "Installed eScriptorium skill from $version at $target"
        Write-Host 'Available on your next Codex turn; restart Codex if it does not appear.'
        Write-Host 'Your MCP connection and credentials were not changed.'
    }
    catch {
        if ($backup -and -not (Test-Path -LiteralPath $target) -and (Test-Path -LiteralPath $backup)) {
            Move-Item -LiteralPath $backup -Destination $target
        }
        throw
    }
    finally {
        if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
        $lock.Dispose()
        Remove-Item -LiteralPath $lockPath -Force
    }
}

Install-EscriptoriumSkill
