@echo off
rem Deck Commander - abre o Assistente do PC (janela com Avancar/Voltar). Duplo clique.
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File "%~dp0assistente.ps1"
