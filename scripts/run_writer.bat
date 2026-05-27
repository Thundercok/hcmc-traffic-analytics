@echo off
chcp 65001 >nul
echo ======================================
echo  TrafficFlow Writer - Chay tren may that
echo ======================================
echo.
echo Cac thong so:
echo   - Database: localhost:5432
echo   - Batch: 100 camera/lan
echo   - Interval: 60 giay
echo   - Concurrency: 12
echo.
echo Khoa CMD nay lai de dung.
echo Ctrl+C de dung writer.
echo ======================================
echo.
cd /d "%~dp0.."
python scripts/run_writer.py
pause
