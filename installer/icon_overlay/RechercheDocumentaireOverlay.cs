// IShellIconOverlayIdentifier — badge « lien » pour les fichiers de l'arborescence
// Categories/ de Recherche Documentaire (hard links vers Documents/).
// Compile en DLL COM regsvr32 (csc /target:library /platform:x64).
// Sert à distinguer visuellement les LIENS (badgés) des fichiers originaux.

using System;
using System.Runtime.InteropServices;
using System.Text;

namespace RechercheDocumentaire
{
    [ComVisible(true)]
    [ClassInterface(ClassInterfaceType.None)]
    [Guid("B4F9A2C1-7E3D-4A8E-9C2F-1D5E6A7B8C9D")]
    public class DocumentLinkOverlay : IShellIconOverlayIdentifier
    {
        // Priorité : Windows limite le nombre d'overlays actifs ; valeur basse = prioritaire.
        public int GetPriority(out int pPriority)
        {
            pPriority = 1;
            return 0;
        }

        // Badge les fichiers situés sous <Categories>/<Catégorie>/[<Tag>/] qui sont
        // des liens durs (NumberOfLinks > 1) vers Documents/.
        public int IsMemberOf(string pwszPath, uint dwAttrib)
        {
            try
            {
                string normalized = pwszPath.Replace('/', '\\');
                int idx = normalized.IndexOf("\\Categories\\", StringComparison.OrdinalIgnoreCase);
                if (idx < 0)
                    return 1; // S_FALSE : pas concerné
                // Cible : au moins un sous-répertoire sous Categories\ (Catégorie[/Tag])
                string rest = normalized.Substring(idx + "\\Categories\\".Length).TrimStart('\\');
                if (rest.Length == 0)
                    return 1;
                if (IsHardLink(pwszPath))
                    return 0; // S_OK : afficher l'overlay
            }
            catch
            {
            }
            return 1;
        }

        public int GetOverlayInfo(StringBuilder pwszIconFile, int cchMax, out int pIndex,
                                   out uint pdwFlags)
        {
            pdwFlags = 1; // ISIOI_ICONFILE
            pIndex = 0;
            string dllDir = System.IO.Path.GetDirectoryName(
                System.Reflection.Assembly.GetExecutingAssembly().Location);
            string icon = System.IO.Path.Combine(dllDir, "doclink.ico");
            pwszIconFile.Clear();
            if (cchMax > icon.Length)
                pwszIconFolderAppend(icon, pwszIconFile);
            return 0;
        }

        private static void pwszIconFolderAppend(string value, StringBuilder sb)
        {
            sb.Append(value);
        }

        private static bool IsHardLink(string path)
        {
            const uint GENERIC_READ = 0x80000000;
            const uint OPEN_EXISTING = 3;
            const uint FILE_FLAG_BACKUP_SEMANTICS = 0x02000000;
            const uint FILE_SHARE_READ = 1;
            IntPtr handle = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, IntPtr.Zero,
                                        OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, IntPtr.Zero);
            if (handle == new IntPtr(-1))
                return false;
            try
            {
                BY_HANDLE_FILE_INFORMATION info;
                if (!GetFileInformationByHandle(handle, out info))
                    return false;
                return info.NumberOfLinks > 1;
            }
            finally
            {
                CloseHandle(handle);
            }
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr CreateFileW(string lpFileName, uint dwDesiredAccess,
            uint dwShareMode, IntPtr lpSecurityAttributes, uint dwCreationDisposition,
            uint dwFlagsAndAttributes, IntPtr hTemplateFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetFileInformationByHandle(IntPtr hFile,
            out BY_HANDLE_FILE_INFORMATION lpFileInformation);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr hObject);

        [StructLayout(LayoutKind.Sequential)]
        private struct BY_HANDLE_FILE_INFORMATION
        {
            public uint FileAttributes;
            public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
            public uint VolumeSerialNumber;
            public uint FileSizeHigh;
            public uint FileSizeLow;
            public uint NumberOfLinks;
            public uint FileIndexHigh;
            public uint FileIndexLow;
        }
    }

    [ComVisible(true)]
    [ComImport]
    [Guid("0C6C4200-C589-11D0-96A8-444553540000")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IShellIconOverlayIdentifier
    {
        [PreserveSig] int GetPriority(out int pPriority);
        [PreserveSig] int IsMemberOf([MarshalAs(UnmanagedType.LPWStr)] string pwszPath, uint dwAttrib);
        [PreserveSig] int GetOverlayInfo(StringBuilder pwszIconFile, int cchMax,
                                         out int pIndex, out uint pdwFlags);
    }
}
