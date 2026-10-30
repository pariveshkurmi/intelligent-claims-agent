Write-Output "=== 1. PYTHON CHECK ==="
try {
    & py -0
} catch {
    Write-Output "py launcher not found"
}
try {
    & python --version
} catch {
    Write-Output "python not in PATH"
}

Write-Output "`n=== 2. GIT CHECK ==="
try {
    & git --version
} catch {
    Write-Output "git NOT found"
}

Write-Output "`n=== 3. DOCKER CHECK ==="
try {
    & docker --version
} catch {
    Write-Output "docker CLI NOT found"
}
$dockerProc = Get-Process -Name "*docker*" -ErrorAction SilentlyContinue
if ($dockerProc) {
    Write-Output "Docker process is running"
} else {
    Write-Output "No Docker process running"
}

Write-Output "`n=== 4. PACKAGE MANAGERS & UTILITIES ==="
try {
    & uv --version
} catch {
    Write-Output "uv NOT installed"
}
try {
    & winget --version
} catch {
    Write-Output "winget NOT installed"
}

