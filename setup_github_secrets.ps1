# GitHub Actions Secrets Setup Script
# Run in PowerShell: .\setup_github_secrets.ps1

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  GitHub Actions Secrets Setup" -ForegroundColor Cyan
Write-Host "============================================`n" -ForegroundColor Cyan

# Check if gh CLI is installed
if (!(Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "❌ GitHub CLI not installed!" -ForegroundColor Red
    Write-Host "`nInstall with: winget install GitHub.cli`n" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ GitHub CLI found`n" -ForegroundColor Green

# Check if authenticated
Write-Host "🔐 Checking GitHub authentication..." -ForegroundColor Yellow
$authStatus = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Not logged in to GitHub!" -ForegroundColor Red
    Write-Host "`nRun: gh auth login`n" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Authenticated with GitHub`n" -ForegroundColor Green

# Set secrets
Write-Host "📝 Setting repository secrets...`n" -ForegroundColor Yellow

$secrets = @{
    "MONITOR_BOT_TOKEN" = "8406974132:AAFE1FBfu27ds6hXGb0jNxWLtl5a04UqvHI"
    "MONITOR_CHAT_ID" = "447705580"
    "SUPABASE_URL" = "https://zrczbdkighpnzenjdsbi.supabase.co"
    "SUPABASE_ANON_KEY" = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpyY3piZGtpZ2hwbnplbmpkc2JpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1OTA0NTgsImV4cCI6MjA3NzE2NjQ1OH0.mA34gm1gqu2EP1TAE8La7sQpZmOOuVqWXSE0dAvtWdo"
    "DAILY_VIDEO_PARENT_FOLDER" = "1ZKnCa-7ieNt3bLhI6f6mCZBmyAP0-dnF"
}

foreach ($key in $secrets.Keys) {
    Write-Host "  Setting $key..." -ForegroundColor Cyan
    $value = $secrets[$key]
    echo $value | gh secret set $key
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    ✅ $key set successfully" -ForegroundColor Green
    } else {
        Write-Host "    ❌ Failed to set $key" -ForegroundColor Red
    }
}

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "✅ All secrets configured!" -ForegroundColor Green
Write-Host "`n📋 Verifying secrets..." -ForegroundColor Yellow

gh secret list

Write-Host "`n🚀 GitHub Actions will now run automatically every 30 minutes!" -ForegroundColor Green
Write-Host "`n💡 To test manually:" -ForegroundColor Yellow
Write-Host "   gh workflow run monitor.yml" -ForegroundColor White
Write-Host "   gh run list --workflow=monitor.yml`n" -ForegroundColor White
