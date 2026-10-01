' CustomAction MSI (VBScript, deferred) : écrit config.yaml à partir des
' propriétés MSI (DRIVE_LETTER, MAIL_*, LAST_RUN).
' Appelée après InstallFiles ; échoue silencieusement si aucune propriété
' n'est fournie (l'utilisateur éditera config.example.yaml).
Option Explicit

Const ForWriting = 2

Function ReadPropOrEmpty(name)
    On Error Resume Next
    ReadPropOrEmpty = Session.Property(name)
    If Err.Number <> 0 Then ReadPropOrEmpty = ""
    On Error GoTo 0
End Function

Sub WriteConfig
    Dim fso, installDir, cfgPath, yaml
    Dim driveLetter, imapUrl, mailLogin, mailPassword, mailDocs, lastRun
    Dim shell, appData, dbDir

    Set fso = CreateObject("Scripting.FileSystemObject")
    Set shell = CreateObject("WScript.Shell")

    installDir = Session.Property("INSTALLDIR")
    cfgPath = fso.BuildPath(installDir, "config.yaml")

    driveLetter = ReadPropOrEmpty("DRIVE_LETTER")
    If driveLetter = "" Then driveLetter = "R:"

    imapUrl = ReadPropOrEmpty("IMAP_URL")
    mailLogin = ReadPropOrEmpty("MAIL_LOGIN")
    mailPassword = ReadPropOrEmpty("MAIL_PASSWORD")
    mailDocs = ReadPropOrEmpty("MAIL_DOCUMENTS_DIR")
    lastRun = ReadPropOrEmpty("LAST_RUN")

    If driveLetter <> "" Or imapUrl <> "" Then
        yaml = "sync:" & vbCrLf
        yaml = yaml & "  drive_letter: """ & driveLetter & """" & vbCrLf
        yaml = yaml & "  local_root: """ & driveLetter & "\""" & vbCrLf
        yaml = yaml & "  db_dir: """ & installDir & ".docsearch""" & vbCrLf
        If imapUrl <> "" Then
            yaml = yaml & "mail:" & vbCrLf
            yaml = yaml & "  imap_url: """ & imapUrl & """" & vbCrLf
            yaml = yaml & "  login: """ & mailLogin & """" & vbCrLf
            yaml = yaml & "  password: """ & mailPassword & """" & vbCrLf
            If mailDocs <> "" Then
                yaml = yaml & "  documents_dir: """ & mailDocs & """" & vbCrLf
            Else
                yaml = yaml & "  documents_dir: """ & driveLetter & "\Documents""" & vbCrLf
            End If
            If lastRun <> "" Then
                yaml = yaml & "  last_run: """ & lastRun & """" & vbCrLf
            End If
        End If

        Dim stream
        Set stream = fso.CreateTextFile(cfgPath, True, False)
        stream.Write yaml
        stream.Close
    End If
End Sub
