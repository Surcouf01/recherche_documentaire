// IShellIconOverlayIdentifier — badge « lien » pour les fichiers de l'arborescence
// Categories/ de Recherche Documentaire (hard links vers Documents/).
// Compile en DLL COM regsvr32 (csc /target:library /platform:x64).
// Sert à distinguer visuellement les LIENS (badgés) des fichiers originaux.

using System;
using System.Collections.Generic;
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

        // Badge les fichiers et répertoires situés sous <root>/Categories/<Catégorie>/[<Tag>/].
        // Répertoires : par construction des vues (cf. pipeline.py), toute catégorie/tag
        // est une vue virtuelle — badge sans test de lien dur (NumberOfLinks d'un dossier
        // NTFS vaut ~sous-dossiers+2 et ne prouve rien).
        // Fichiers : liens durs vers <root>/Documents/, vérifiés par IDENTITÉ :
        // NumberOfLinks>1 en local, sinon comparaison du FileIndex (ou, à défaut sur
        // les partages SMB qui ne le fournissent pas, de la taille + horodatages) avec
        // les fichiers de l'arborescence Documents/ voisine.
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
                if ((dwAttrib & 0x10) != 0 || IsDirectory(pwszPath))
                    return 0; // S_OK : vue Categories — badge direct
                string documentsDir = System.IO.Path.Combine(
                    normalized.Substring(0, idx), "Documents");
                if (IsHardLink(pwszPath, documentsDir))
                    return 0; // S_OK : afficher l'overlay
            }
            catch
            {
            }
            return 1;
        }

        private static bool IsDirectory(string path)
        {
            Info info = GetInfo(path);
            return info != null && (info.Attributes & 0x10) != 0;
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

        private static bool IsHardLink(string path, string documentsDir)
        {
            Info info = GetInfo(path);
            if (info == null)
                return false;
            // Local : NumberOfLinks est fiable et ne coûte rien.
            if (info.NumberOfLinks > 1)
                return true;
            // Réseau : NumberOfLinks vaut souvent 1 même pour de vrais liens durs.
            // On compare alors l'identité du fichier avec ceux de Documents/.
            ScanCache cache = GetDocumentsCache(documentsDir);
            if (cache == null)
                return false;
            if (info.IndexHigh != 0 || info.IndexLow != 0)
                return cache.Exact.Contains(ExactKey(info));
            // FileIndex non fourni par le serveur (fréquent en SMB) : repli sur
            // taille + horodatages (création/modification), identiques pour deux
            // noms d'un même lien dur.
            return cache.Fuzzy.Contains(FuzzyKey(info));
        }

        private sealed class Info
        {
            public uint Attributes;
            public uint NumberOfLinks;
            public uint Volume;
            public uint IndexHigh;
            public uint IndexLow;
            public long Size;
            public long CreationTime;
            public long LastWriteTime;
        }

        private sealed class ScanCache
        {
            public HashSet<string> Exact = new HashSet<string>();
            public HashSet<string> Fuzzy = new HashSet<string>();
        }

        // IsMemberOf est appelé pour chaque fichier affiché : le balayage de
        // Documents/ est mis en cache (remplacé atomiquement) pour limiter le coût.
        private static readonly TimeSpan CacheTtl = TimeSpan.FromMinutes(5);
        private static readonly object CacheLock = new object();
        private static readonly Dictionary<string, ScanCache> Caches =
            new Dictionary<string, ScanCache>(StringComparer.OrdinalIgnoreCase);
        private static readonly Dictionary<string, DateTime> CacheStamps =
            new Dictionary<string, DateTime>(StringComparer.OrdinalIgnoreCase);

        private static ScanCache GetDocumentsCache(string documentsDir)
        {
            lock (CacheLock)
            {
                DateTime stamp;
                ScanCache fresh;
                if (CacheStamps.TryGetValue(documentsDir, out stamp) &&
                    DateTime.UtcNow - stamp < CacheTtl &&
                    Caches.TryGetValue(documentsDir, out fresh))
                    return fresh;
            }
            ScanCache built = BuildDocumentsCache(documentsDir);
            lock (CacheLock)
            {
                Caches[documentsDir] = built;
                CacheStamps[documentsDir] = DateTime.UtcNow;
            }
            return built;
        }

        private static ScanCache BuildDocumentsCache(string documentsDir)
        {
            ScanCache cache = new ScanCache();
            try
            {
                if (!System.IO.Directory.Exists(documentsDir))
                    return cache;
                foreach (string file in System.IO.Directory.EnumerateFiles(
                    documentsDir, "*", System.IO.SearchOption.AllDirectories))
                {
                    Info info = GetInfo(file);
                    if (info == null)
                        continue;
                    cache.Exact.Add(ExactKey(info));
                    cache.Fuzzy.Add(FuzzyKey(info));
                }
            }
            catch
            {
                // Partage inaccessible : cache vide, pas d'overlay.
            }
            return cache;
        }

        private static string ExactKey(Info i)
        {
            return i.Volume.ToString() + ":" + i.IndexHigh.ToString("X8") + i.IndexLow.ToString("X8");
        }

        private static string FuzzyKey(Info i)
        {
            return i.Size.ToString() + ":" + i.CreationTime.ToString() + ":" + i.LastWriteTime.ToString();
        }

        private static Info GetInfo(string path)
        {
            const uint GENERIC_READ = 0x80000000;
            const uint OPEN_EXISTING = 3;
            const uint FILE_FLAG_BACKUP_SEMANTICS = 0x02000000;
            const uint FILE_SHARE_READ = 1;
            IntPtr handle = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, IntPtr.Zero,
                                        OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, IntPtr.Zero);
            if (handle == new IntPtr(-1))
                return null;
            try
            {
                BY_HANDLE_FILE_INFORMATION raw;
                if (!GetFileInformationByHandle(handle, out raw))
                    return null;
                return new Info
                {
                    Attributes = raw.FileAttributes,
                    NumberOfLinks = raw.NumberOfLinks,
                    Volume = raw.VolumeSerialNumber,
                    IndexHigh = raw.FileIndexHigh,
                    IndexLow = raw.FileIndexLow,
                    Size = ((long)raw.FileSizeHigh << 32) | raw.FileSizeLow,
                    CreationTime = FileTimeToLong(raw.CreationTime),
                    LastWriteTime = FileTimeToLong(raw.LastWriteTime)
                };
            }
            finally
            {
                CloseHandle(handle);
            }
        }

        private static long FileTimeToLong(System.Runtime.InteropServices.ComTypes.FILETIME ft)
        {
            return ((long)(uint)ft.dwHighDateTime << 32) | (uint)ft.dwLowDateTime;
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
