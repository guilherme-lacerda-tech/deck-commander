' Deck Commander — roda um comando SEM abrir janela nenhuma (o powershell -WindowStyle Hidden ainda pisca).
' Uso (tarefa agendada): wscript.exe "...\oculto.vbs" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "...\script.ps1"
Dim args, i, cmd
Set args = WScript.Arguments
cmd = ""
For i = 0 To args.Count - 1
    If InStr(args(i), " ") > 0 Then
        cmd = cmd & """" & args(i) & """ "
    Else
        cmd = cmd & args(i) & " "
    End If
Next
CreateObject("WScript.Shell").Run Trim(cmd), 0, True
