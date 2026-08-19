' Site Recon Dashboard - start the local server hidden, no console window.
' Works from wherever the repo is cloned: paths are derived from this file's
' own location, and Python is found on PATH rather than hardcoded.
Option Explicit
Dim fso, sh, repo, started

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

' This script lives in <repo>\dashboard, so the repo is its parent's parent.
repo = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
If Not fso.FileExists(fso.BuildPath(repo, "dashboard\api.py")) Then WScript.Quit 0

sh.CurrentDirectory = repo

' pythonw.exe runs without a console window; python.exe is the fallback for
' installs that do not ship it. 0 = hidden window, False = do not wait.
started = False
On Error Resume Next
sh.Run """pythonw.exe"" dashboard\api.py 8080", 0, False
If Err.Number = 0 Then started = True
Err.Clear
If Not started Then
    sh.Run """python.exe"" dashboard\api.py 8080", 0, False
End If
On Error GoTo 0
