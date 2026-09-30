' CustomAction MSI (VBScript, deferred) : écrit config.yaml à partir des
' propriétés MSI (QUICKCONNECT_ID, NAS_*, DRIVE_LETTER, MAIL_*, LAST_RUN).
' Appelée après InstallFiles ; échoue silencieusement si aucune propriété
' de connexion n'est fournie (l'utilisateur éditera config.example.yaml).

Option Explicit

Const ForWriting = 2

Function ReadPropOrEmpty(name)
    On Error Resume Next
    ReadPropOrEmpty = Session.Property(name)
    If Err.Number <> 0 Then ReadPropOrEmpty = ""
    On Error GoTo 0
End Function

Sub WriteConfig
    Dim fso, installDir, cfgPath, yaml, quickconnect, nasLogin, nasPassword
    Dim nasDocs, driveLetter, imapUrl, mailLogin, mailPassword, mailDocs, lastRun
    Dim shell, appData, dbDir

    Set fso = CreateObject("Scripting.FileSystemObject")
    Set shell = CreateObject("WScript.Shell")

    installDir = Session.Property("INSTALLDIR")
    cfgPath = fso.BuildPath(installDir, "config.yaml")

    quickconnect = ReadPropOrEmpty("QUICKCONNECT_ID")
    nasLogin = ReadPropOrEmpty("NAS_LOGIN")
    nasPassword = ReadPropOrEmpty("NAS_PASSWORD")
    nasDocs = ReadPropOrEmpty("NAS_DOCUMENTS_DIR")
    If nasDocs = "" Then nasDocs = "/volume1/docs/Documents"
    driveLetter = ReadPropOrEmpty("DRIVE_LETTER")
    If driveLetter = "" Then driveLetter = "R:"
    imapUrl = ReadPropOrEmpty("IMAP_URL")
    mailLogin = ReadPropOrEmpty("MAIL_LOGIN")
    mailPassword = ReadPropOrEmpty("MAIL_PASSWORD")
    mailDocs = ReadPropOrEmpty("MAIL_DOCUMENTS_DIR")
    lastRun = ReadPropOrEmpty("LAST_RUN")

    If quickconnect <> "" Or imapUrl <> "" Then
        yaml = "sync:" & vbCrLf
        yaml = yaml & "  nas_quickconnect_id: """ & quickconnect & """" & vbCrLf
        yaml = yaml & "  nas_login: """ & nasLogin & """" & vbCrLf
        yaml = yaml & "  nas_password: """ & nasPassword & """" & vbCrLf
        yaml = yaml & "  nas_documents_dir: """ & nasDocs & """" & vbCrLf
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
