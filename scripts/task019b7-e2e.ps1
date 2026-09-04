Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..')).Path
$GoSpiderDir = Join-Path $RepoRoot 'go-spider'
$ComposePath = Join-Path $RepoRoot 'tests\integration\task019b7\compose.yml'
$MigrationPath = 'migrations/mysql/0001_articles_task_articles_v2.sql'
$MigrationContainerPath = '/migrations/0001_articles_task_articles_v2.sql'

$ProjectName = $null
$Failed = $false

function Assert-DockerAndGo {
    $dockerVersion = & docker version 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $dockerVersion) {
        throw 'Docker daemon is not available.'
    }
    $info = (& docker info --format '{{.ServerVersion}}|{{.OSType}}|{{.Architecture}}' 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $info -or $info -notmatch '^[^|]+\|linux\|') {
        throw 'Docker server is not a Linux container engine.'
    }
    & docker context show | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'docker context show failed.' }
    & docker compose version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'docker compose is not available.' }

    $env:Path = 'C:\msys64\ucrt64\bin;' + $env:Path
    $env:CC = 'C:\msys64\ucrt64\bin\gcc.exe'
    $env:CXX = 'C:\msys64\ucrt64\bin\g++.exe'
    $env:CGO_ENABLED = '1'
    & go version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'go is not available.' }
    & gcc --version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'gcc is not available.' }
    $lib = & gcc --print-file-name libsynchronization.a
    if (-not $lib -or -not (Test-Path -LiteralPath $lib)) {
        throw 'libsynchronization.a is not available.'
    }
}

function New-UniqueProjectName {
    while ($true) {
        $bytes = New-Object byte[] 6
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
        $hex = ($bytes | ForEach-Object { $_.ToString('x2') }) -join ''
        $candidate = 'crawler019b7-' + $hex
        if ($candidate -notmatch '^crawler019b7-[a-f0-9]{12}$') { continue }
        $containers = @(& docker ps -a --filter "label=com.docker.compose.project=$candidate" --format '{{.ID}}')
        $networks = @(& docker network ls --filter "label=com.docker.compose.project=$candidate" --format '{{.ID}}')
        $volumes = @(& docker volume ls --filter "label=com.docker.compose.project=$candidate" --format '{{.Name}}')
        if ($containers.Count -eq 0 -and $networks.Count -eq 0 -and $volumes.Count -eq 0) {
            return $candidate
        }
    }
}

function Get-ComposePort {
    param([string]$Service, [string]$ContainerPort)
    $line = (& docker compose --project-name $ProjectName --file $ComposePath port $Service $ContainerPort | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0 -or -not $line) {
        throw "Unable to resolve port for $Service."
    }
    if ($line -notmatch '^127\.0\.0\.1:(\d+)$') {
        throw "Unexpected port mapping for $Service : $line"
    }
    return [int]$Matches[1]
}

function Invoke-GoTest {
    param([string]$Run, [string]$Pkg, [switch]$Race)
    Push-Location $GoSpiderDir
    try {
        if ($Race) {
            & go test -race -mod=readonly -count=1 -run $Run $Pkg
        } else {
            & go test -mod=readonly -count=1 -run $Run $Pkg
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Go test failed: $Run $Pkg"
        }
    } finally {
        Pop-Location
    }
}

function Invoke-ComposeDown {
    & docker compose --project-name $ProjectName --file $ComposePath down --volumes --remove-orphans | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "compose down failed for $ProjectName" }
}

function Assert-NoResources {
    $containers = @(& docker ps -a --filter "label=com.docker.compose.project=$ProjectName" --format '{{.ID}}')
    $networks = @(& docker network ls --filter "label=com.docker.compose.project=$ProjectName" --format '{{.ID}}')
    $volumes = @(& docker volume ls --filter "label=com.docker.compose.project=$ProjectName" --format '{{.Name}}')
    if ($containers.Count -ne 0 -or $networks.Count -ne 0 -or $volumes.Count -ne 0) {
        throw "Residual B7 resources: containers=$($containers.Count) networks=$($networks.Count) volumes=$($volumes.Count)"
    }
}

function Remove-TempEnv {
    foreach ($name in @('TASK019B7_E2E','TASK019B7_MYSQL_DSN','TASK019B7_REDIS_ADDR','TASK019B7_MYSQL_ROOT_PASSWORD','TASK019B7_MYSQL_USER_PASSWORD')) {
        if (Test-Path "Env:$name") { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
    }
}

try {
    Assert-DockerAndGo
    $ProjectName = New-UniqueProjectName
    $env:TASK019B7_E2E = '1'
    $rootBytes = New-Object byte[] 16
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($rootBytes)
    $userBytes = New-Object byte[] 16
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($userBytes)
    $env:TASK019B7_MYSQL_ROOT_PASSWORD = ($rootBytes | ForEach-Object { $_.ToString('x2') }) -join ''
    $env:TASK019B7_MYSQL_USER_PASSWORD = ($userBytes | ForEach-Object { $_.ToString('x2') }) -join ''
    $env:TASK019B7_MYSQL_DSN = ''
    $env:TASK019B7_REDIS_ADDR = ''

    & docker compose --project-name $ProjectName --file $ComposePath config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'docker compose config --quiet failed.' }

    & docker compose --project-name $ProjectName --file $ComposePath up --detach --wait --wait-timeout 120
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up --wait failed.' }

    $mysqlPort = Get-ComposePort 'mysql' '3306'
    $redisPort = Get-ComposePort 'redis' '6379'
    $env:TASK019B7_MYSQL_DSN = "crawler_b7:$($env:TASK019B7_MYSQL_USER_PASSWORD)@tcp(127.0.0.1:$mysqlPort)/crawler_b7?charset=utf8mb4&parseTime=True"
    $env:TASK019B7_REDIS_ADDR = "127.0.0.1:$redisPort"

    Invoke-GoTest '^TestTask019B7LegacyBootstrap$' './internal/store'

    $migrationCommand = 'MYSQL_PWD="$MYSQL_PASSWORD" mysql -h127.0.0.1 -ucrawler_b7 crawler_b7 < ' + $MigrationContainerPath
    & docker compose --project-name $ProjectName --file $ComposePath exec -T mysql sh -c $migrationCommand
    if ($LASTEXITCODE -ne 0) { throw 'migration run 1 failed.' }
    & docker compose --project-name $ProjectName --file $ComposePath exec -T mysql sh -c $migrationCommand
    if ($LASTEXITCODE -ne 0) { throw 'migration run 2 failed.' }

    Invoke-GoTest '^TestTask019B7SchemaAfterMigration$' './internal/store'
    Invoke-GoTest '^TestTask019B7ResultConsumerE2E$' './internal/worker'
    Invoke-GoTest '^TestTask019B7ResultConsumerE2E$' './internal/worker' -Race
}
catch {
    $Failed = $true
    Write-Error $_
    if ($ProjectName) {
        & docker compose --project-name $ProjectName --file $ComposePath ps | Out-Host
        & docker compose --project-name $ProjectName --file $ComposePath logs --no-color --tail 200 mysql | Out-Host
        & docker compose --project-name $ProjectName --file $ComposePath logs --no-color --tail 200 redis | Out-Host
    }
}
finally {
    if ($ProjectName) {
        $downAttempts = 0
        while ($downAttempts -lt 2) {
            try {
                Invoke-ComposeDown
                Assert-NoResources
                break
            } catch {
                $downAttempts++
                if ($downAttempts -ge 2) {
                    Write-Error $_
                    throw
                }
                Start-Sleep -Seconds 2
            }
        }
    }
    Remove-TempEnv
}