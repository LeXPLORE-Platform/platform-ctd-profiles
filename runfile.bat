@echo off
setlocal enabledelayedexpansion

:: Ensure correct location
cd "C:\Users\Seatronic 1147\Documents\Data_Lexplore\git\ctd-profiles"

:: Load input variables
call "scripts\input_batch.bat"

%pythonenv% %script%

:: Upload new data
%pythonenv% %upload% -w

:: Send notification to Datalakes API
curl "https://api.datalakes-eawag.ch/update/875"
timeout 20
curl "https://api.datalakes-eawag.ch/update/674"
