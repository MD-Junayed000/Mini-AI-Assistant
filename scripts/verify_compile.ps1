$venvPy = "d:\Mini_AI_Assistant\.venv\Scripts\python.exe"
$files = @(
    "d:\Mini_AI_Assistant\backend\memory.py",
    "d:\Mini_AI_Assistant\backend\routes\chat.py"
)
$ok = $true
foreach ($f in $files) {
    & $venvPy -m py_compile $f
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: $f"
        $ok = $false
    } else {
        Write-Host "OK  : $f"
    }
}
if (-not $ok) { exit 1 } else { exit 0 }