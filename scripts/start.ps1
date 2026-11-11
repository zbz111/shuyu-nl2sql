# 一键启动（Windows PowerShell）
# 用法：.\scripts\start.ps1   /   .\scripts\start.ps1 -Port 8020

param(
    [int]$Port = 8010,
    [string]$HostAddr = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[1/3] 创建虚拟环境 ..." -ForegroundColor Cyan
    try { python -m venv .venv }
    catch {
        python -m venv --without-pip .venv
        python -m pip --python .\.venv\Scripts\python.exe install -r requirements.txt
    }
}

$py = ".\.venv\Scripts\python.exe"

if (-not (Test-Path ".venv\Lib\site-packages\fastapi")) {
    Write-Host "[2/3] 安装依赖 ..." -ForegroundColor Cyan
    & $py -m pip install -r requirements.txt
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已生成 .env，请按需修改模型配置。" -ForegroundColor Yellow
}

if (-not (Test-Path "data\sales.db")) {
    Write-Host "生成演示数据库 ..." -ForegroundColor Cyan
    & $py scripts\seed_demo.py
}

Write-Host "[3/3] 启动服务： http://${HostAddr}:${Port}" -ForegroundColor Green
& $py -m uvicorn app.main:app --host $HostAddr --port $Port
