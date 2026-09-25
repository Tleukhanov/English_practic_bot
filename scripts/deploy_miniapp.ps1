[CmdletBinding()]
param(
    [int]$Port = 0
)

Set-StrictMode -Version Latest

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

function Test-LocalPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.ConnectAsync("127.0.0.1", $Port)
        if (-not $connection.Wait(1000)) {
            return $false
        }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Show-NginxExample {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $config = @'
server {
    listen 80;
    server_name miniapp.example.com;

    client_max_body_size 25m;

    location / {
        proxy_pass http://127.0.0.1:__PORT__;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
'@

    Write-Host "Nginx example (replace miniapp.example.com):" -ForegroundColor Cyan
    Write-Host $config.Replace("__PORT__", [string]$Port)
}

function Show-CertbotSteps {
    Write-Host "Permanent HTTPS checklist:" -ForegroundColor Cyan
    Write-Host "1. Create an A/AAAA DNS record for miniapp.example.com to the host."
    Write-Host "2. On Ubuntu/Debian install nginx and certbot:"
    Write-Host "   sudo apt update"
    Write-Host "   sudo apt install nginx certbot python3-certbot-nginx"
    Write-Host "3. Save the nginx block as /etc/nginx/sites-available/english-miniapp."
    Write-Host "4. Enable it and validate nginx:"
    Write-Host "   sudo ln -s /etc/nginx/sites-available/english-miniapp /etc/nginx/sites-enabled/english-miniapp"
    Write-Host "   sudo nginx -t"
    Write-Host "   sudo systemctl reload nginx"
    Write-Host "5. Issue and enable HTTPS:"
    Write-Host "   sudo certbot --nginx -d miniapp.example.com"
    Write-Host "6. Set these values in .env, restart the bot, and verify:"
    Write-Host "   WEBAPP_URL=https://miniapp.example.com"
    Write-Host "   WEBAPP_HOST=127.0.0.1"
    Write-Host "   curl -fsS https://miniapp.example.com/api/health"
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"

if ($Port -eq 0) {
    $Port = Get-WebAppPort -EnvPath $envPath
} elseif ($Port -lt 1 -or $Port -gt 65535) {
    Write-Error "Port must be between 1 and 65535."
    exit 2
}

Write-Host "Permanent Mini App deployment checklist (no system changes will be made)."
Write-Host "Configured local port: $Port"

if (Test-LocalPort -Port $Port) {
    Write-Host "Port $Port is open on 127.0.0.1." -ForegroundColor Green
} else {
    Write-Warning "Nothing is listening on 127.0.0.1:$Port. Start the bot before production use."
}

Show-NginxExample -Port $Port
Show-CertbotSteps
