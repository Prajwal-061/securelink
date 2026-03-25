@echo off
setlocal

set ROOT_DIR=%~dp0\..
pushd %ROOT_DIR%

if "%PYTHON_BIN%"=="" (
  set PYTHON_BIN=%ROOT_DIR%\venv\Scripts\python.exe
)

echo [SecureLink] Build root: %ROOT_DIR%
echo [SecureLink] Python: %PYTHON_BIN%

%PYTHON_BIN% -m pip install --upgrade pip pyinstaller
if errorlevel 1 goto :error

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [SecureLink] Building one-dir from spec...
%PYTHON_BIN% -m PyInstaller --noconfirm SecureLink.spec
if errorlevel 1 goto :error

echo [SecureLink] Building one-file fallback...
%PYTHON_BIN% -m PyInstaller --noconfirm --onefile --windowed --name SecureLinkOneFile seclink_main.py
if errorlevel 1 goto :error

echo [SecureLink] Build complete
echo Artifacts:
echo   - dist\SecureLink\
echo   - dist\SecureLinkOneFile.exe

popd
exit /b 0

:error
echo [SecureLink] Build failed.
popd
exit /b 1
