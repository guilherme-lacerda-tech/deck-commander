@echo off
rem Deck Commander - transfere um jogo do Steam Deck para este PC (jogo + emulador + config + saves).
rem Duplo clique: pergunta o jogo. Ou: transferir-do-deck.bat -Jogo <id> [-Destino D:\Pasta] [-SoInstalar]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0transferir-do-deck.ps1" %*
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
