@echo off
echo Abrindo o WSL para iniciar o ngrok...
wsl -e bash -c "ngrok start msb_app"

exit