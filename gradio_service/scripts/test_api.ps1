param([string]$BaseUrl = "http://127.0.0.1:8000")

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TempImage = Join-Path ([System.IO.Path]::GetTempPath()) "gradio-smoke-test.png"
$Png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
[System.IO.File]::WriteAllBytes($TempImage, [Convert]::FromBase64String($Png))

try {
    $Health = Invoke-RestMethod -Uri "$BaseUrl/api/health"
    if ($Health.status -ne "ok") { throw "Health check failed" }
    Write-Host "PASS health"

    $Raw = & curl.exe -sS -X POST -F "files=@$TempImage;type=image/png" -F "input_kind=image" "$BaseUrl/api/v1/jobs/inference"
    $Created = $Raw | ConvertFrom-Json
    if (-not $Created.job_id) { throw "Job creation failed: $Raw" }
    Write-Host "PASS create job"

    for ($i = 0; $i -lt 100; $i++) {
        $Job = Invoke-RestMethod -Uri "$BaseUrl/api/v1/jobs/$($Created.job_id)"
        if ($Job.status -in @("success", "failed")) { break }
        Start-Sleep -Milliseconds 100
    }
    if ($Job.status -ne "success") { throw "Job did not succeed: $($Job.status)" }
    Write-Host "PASS poll job"

    $Result = Invoke-RestMethod -Uri "$BaseUrl/api/v1/jobs/$($Created.job_id)/result"
    if ($Result.contract_version -ne "0.1") { throw "Unexpected contract version" }
    Write-Host "PASS result"
}
finally {
    Remove-Item -LiteralPath $TempImage -ErrorAction SilentlyContinue
}
