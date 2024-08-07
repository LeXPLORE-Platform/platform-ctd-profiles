@echo off
setlocal enabledelayedexpansion

:: Ensure correct location
cd "C:\Users\Seatronic 1147\Documents\Data_Lexplore\git\ctd-profiles"

:: Ensure repo is up to date
:: git stash
:: git pull

:: Load input variables
call "scripts\input_batch.bat"

%pythonenv% %script%

:: Push changes to remote repository
git add --all
git commit -m "Auto Upload"
git push