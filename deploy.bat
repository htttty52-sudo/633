@echo off
chcp 65001 >nul
echo ============================================
echo  嵌入式Linux系统构建与配置平台 - 一键部署
echo ============================================
echo.

echo [1/4] 构建并启动所有服务 (含3个Worker)...
docker compose up --build -d --scale worker=3
if %errorlevel% neq 0 (
    echo 启动失败，请检查Docker是否运行
    pause
    exit /b 1
)

echo.
echo [2/4] 等待服务就绪...
timeout /t 10 /nobreak >nul

echo.
echo [3/4] 检查服务健康状态...
docker compose ps

echo.
echo [4/4] 初始化1000台模拟设备数据...
docker compose exec -T backend python -m scripts.seed_devices

echo.
echo ============================================
echo  部署完成!
echo ============================================
echo.
echo  前端:     http://localhost:3000
echo  后端API:  http://localhost:8000/docs
echo  系统看板: http://localhost:3000/dashboard
echo.
echo  管理命令:
echo    查看日志:     docker compose logs -f
echo    Worker日志:   docker compose logs -f worker
echo    扩缩Worker:   docker compose up -d --scale worker=5
echo    停止服务:     docker compose down
echo    清理数据:     docker compose down -v
echo.
pause
