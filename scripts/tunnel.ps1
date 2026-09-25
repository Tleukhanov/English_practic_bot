[CmdletBinding()]
param(
    [int]$Port = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

function Get-WebAppPort {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EnvPath
    )

    $resolvedPort = 8081
    if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) {
        return $resolvedPort
    }

    foreach ($line in [System.IO.File]::ReadLines($EnvPath)) {
        if ($line -notmatch '^\s*WEBAPP_PORT\s*=\s*([^#]*)') {
            continue
        }

        $rawPort = $Matches[1].Trim()
        if (
            $rawPort.Length -ge 2 -and
            (
                ($rawPort.StartsWith('"') -and $rawPort.EndsWith('"')) -or
                ($rawPort.StartsWith("'") -and $rawPort.EndsWith("'"))
            )
        ) {
            $rawPort = $rawPort.Substring(1, $rawPort.Length - 2).Trim()
        }

        $parsedPort = 0
        if (
            [int]::TryParse($rawPort, [ref]$parsedPort) -and
            $parsedPort -ge 1 -and
            $parsedPort -le 65535
        ) {
            $resolvedPort = $parsedPort
        } else {
            Write-Warning "Invalid WEBAPP_PORT in .env; using 8081."
        }
        break
    }

    return $resolvedPort
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"

if ($Port -eq 0) {
    $Port = Get-WebAppPort -EnvPath $envPath
} elseif ($Port -lt 1 -or $Port -gt 65535) {
    Write-Error "Port must be between 1 and 65535."
    exit 2
}

$cloudflaredCommands = @(
    Get-Command -Name "cloudflared" -CommandType Application -ErrorAction SilentlyContinue
)
if ($cloudflaredCommands.Count -eq 0) {
    Write-Error "cloudflared was not found in PATH."
    Write-Host "Install it on Windows with:"
    Write-Host "  winget install cloudflare/cloudflared"
    Write-Host "Then open a new PowerShell window and run this script again."
    exit 1
}

$cloudflared = $cloudflaredCommands[0]
$targetUrl = "http://127.0.0.1:$Port"
$urlPattern = 'https://[a-zA-Z0-9-]+\.trycloudflare\.com'
$state = @{ UrlShown = $false }

Write-Host "Starting cloudflared quick tunnel for $targetUrl"
Write-Host "Keep this window open. Press Ctrl+C to stop the tunnel."
Write-Host "This script does not modify .env."

& $cloudflared.Source tunnel --url $targetUrl 2>&1 | ForEach-Object {
    $line = $_.ToString()
    Write-Host $line

    if (-not $state.UrlShown -and $line -match $urlPattern) {
        $publicUrl = $Matches[0]
        $state.UrlShown = $true
        Write-Host ""
        Write-Host "Copy this value into .env, then restart the bot:" -ForegroundColor Cyan
        Write-Host "  WEBAPP_URL=$publicUrl" -ForegroundColor Green
        Write-Host "The .env file is not changed automatically." -ForegroundColor Yellow
    }
}

$exitCode = $LASTEXITCODE
if (-not $state.UrlShown) {
    Write-Host ""
    Write-Host "Copy the HTTPS URL printed by cloudflared into:" -ForegroundColor Cyan
    Write-Host "  WEBAPP_URL=https://<quick-tunnel-url>" -ForegroundColor Green
}

if ($exitCode -ne 0) {
    exit $exitCode
}
