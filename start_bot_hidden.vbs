' Starts the One Piece restock bot and its Discord commands with no windows.
' A shortcut to this file in the Startup folder runs it every time you log in.
Set shell = CreateObject("WScript.Shell")
folder = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
shell.Run """" & folder & "\run_forever.bat""", 0, False
shell.Run """" & folder & "\run_commands.bat""", 0, False
