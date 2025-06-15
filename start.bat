@echo off

echo [+] Aktywacja srodowiska wirtualnego (env\Scripts\activate)...
CALL env\Scripts\activate

if "%VIRTUAL_ENV%"=="" (
    echo [!] Blad: Nie udalo sie aktywowac srodowiska wirtualnego.
    echo     Upewnij sie, ze plik start.bat jest w tym samym folderze co katalog 'env'.
    pause
    exit /b 1
) else (
    echo [+] Srodowisko wirtualne aktywowane: %VIRTUAL_ENV%
)


echo [+] Sprawdzanie, czy biblioteki sa zainstalowane...

pip freeze | findstr /I /C:"pyserial" > nul

if %errorlevel% equ 0 (
    echo [+] Biblioteki juz sa zainstalowane, pomijam instalacje.
) else (
    echo [+] Instalacja wymaganych bibliotek z requirements.txt...
    pip install -r requirements.txt
    
   
    if %errorlevel% neq 0 (
        echo [!] Blad podczas instalacji bibliotek. Sprawdz plik requirements.txt i polaczenie z internetem.
        pause
        exit /b 1
    )
)

echo [+] Uruchamianie aplikacji (python main.py)...
python main.py

echo.
echo [+] Zakończono działanie programu. Nacisnij dowolny klawisz, aby zamknąć to okno...
pause