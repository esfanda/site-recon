' Site Recon Dashboard - start the local server hidden, no console window.
' Runs from the repo so relative paths (config, data, reports) resolve.
Option Explicit
Dim fso, sh, repo, py

repo = "D:\github\site-recon"
py = "C:\Users\esfan\AppData\Local\Programs\Python\Python314\pythonw.exe"

Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FolderExists(repo) Then WScript.Quit 0
If Not fso.FileExists(py) Then WScript.Quit 0

Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = repo
' 0 = hidden window, False = do not wait
sh.Run """" & py & """ dashboard\api.py 8080", 0, False
