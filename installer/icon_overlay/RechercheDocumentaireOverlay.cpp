// IShellIconOverlayIdentifier - badge « lien » pour l'arborescence Categories/
// de Recherche Documentaire (liens durs vers Documents/).
// Portage natif (C++/Win32) : le shell moderne refuse de charger le CLR .NET
// dans explorer.exe pour les extensions tierces ; une DLL native n'a pas
// cette limitation (même approche que TortoiseGit/Dropbox).
//
// Compilation (MSVC) :
//   cl /nologo /LD /O2 /EHsc RechercheDocumentaireOverlay.cpp /link /DLL /OUT:RechercheDocumentaireOverlay.dll
//   (ou MinGW : g++ -shared -O2 -o RechercheDocumentaireOverlay.dll RechercheDocumentaireOverlay.cpp -static)
// Enregistrement : voir register_overlay.ps1 (InprocServer32 = chemin de la DLL).

#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <cwctype>
#include <new>
#include <vector>
#include <shlobj.h>
#include <string>
#include <unordered_set>
#include <mutex>
#include <chrono>

// {B4F9A2C1-7E3D-4A8E-9C2F-1D5E6A7B8C9D}
static const CLSID CLSID_DocumentLinkOverlay =
{ 0xB4F9A2C1, 0x7E3D, 0x4A8E, { 0x9C, 0x2F, 0x1D, 0x5E, 0x6A, 0x7B, 0x8C, 0x9D } };

static HMODULE g_hModule = nullptr;

struct FileInfo
{
    DWORD attributes;
    DWORD numberOfLinks;
    DWORD volume;
    DWORD indexHigh;
    DWORD indexLow;
    long long size;
    long long creationTime;
    long long lastWriteTime;
};

static long long FileTimeToLong(const FILETIME& ft)
{
    return (static_cast<long long>(ft.dwHighDateTime) << 32) | ft.dwLowDateTime;
}

static bool GetInfo(const wchar_t* path, FileInfo& info)
{
    HANDLE handle = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, nullptr,
                                OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, nullptr);
    if (handle == INVALID_HANDLE_VALUE)
        return false;
    BY_HANDLE_FILE_INFORMATION raw;
    bool ok = GetFileInformationByHandle(handle, &raw) != FALSE;
    CloseHandle(handle);
    if (!ok)
        return false;
    info.attributes = raw.dwFileAttributes;
    info.numberOfLinks = raw.nNumberOfLinks;
    info.volume = raw.dwVolumeSerialNumber;
    info.indexHigh = raw.nFileIndexHigh;
    info.indexLow = raw.nFileIndexLow;
    info.size = (static_cast<long long>(raw.nFileSizeHigh) << 32) | raw.nFileSizeLow;
    info.creationTime = FileTimeToLong(raw.ftCreationTime);
    info.lastWriteTime = FileTimeToLong(raw.ftLastWriteTime);
    return true;
}

static bool IsDirectory(const wchar_t* path)
{
    FileInfo info;
    if (!GetInfo(path, info))
        return false;
    return (info.attributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
}

struct ScanCache
{
    std::unordered_set<std::wstring> exact;
    std::unordered_set<std::wstring> fuzzy;
};

static std::wstring ExactKey(const FileInfo& i)
{
    wchar_t buf[64];
    swprintf_s(buf, L"%u:%08X%08X", i.volume, i.indexHigh, i.indexLow);
    return buf;
}

static std::wstring FuzzyKey(const FileInfo& i)
{
    wchar_t buf[96];
    swprintf_s(buf, L"%lld:%lld:%lld", i.size, i.creationTime, i.lastWriteTime);
    return buf;
}

// IsMemberOf est appelé pour chaque fichier affiché : le balayage de
// Documents/ est mis en cache (TTL 5 min) pour limiter le coût.
static const double kCacheTtlSeconds = 300.0;

struct CacheEntry
{
    std::chrono::steady_clock::time_point stamp;
    ScanCache cache;
};

static std::mutex g_cacheMutex;
static std::wstring g_cacheDir;
static CacheEntry g_cacheEntry;

static void BuildDocumentsCache(const std::wstring& documentsDir, ScanCache& cache)
{
    WIN32_FIND_DATAW fd;
    std::wstring pattern = documentsDir;
    if (!pattern.empty() && pattern.back() != L'\\')
        pattern += L'\\';
    std::wstring firstPattern = pattern + L"*";
    HANDLE find = FindFirstFileW(firstPattern.c_str(), &fd);
    if (find == INVALID_HANDLE_VALUE)
        return;
    std::vector<std::wstring> dirs;
    do
    {
        if (wcscmp(fd.cFileName, L".") == 0 || wcscmp(fd.cFileName, L"..") == 0)
            continue;
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
            dirs.push_back(fd.cFileName);
        else
        {
            FileInfo info;
            std::wstring file = pattern + fd.cFileName;
            if (GetInfo(file.c_str(), info))
            {
                cache.exact.insert(ExactKey(info));
                cache.fuzzy.insert(FuzzyKey(info));
            }
        }
    } while (FindNextFileW(find, &fd));
    FindClose(find);
    for (const auto& dir : dirs)
    {
        std::wstring sub = pattern + dir;
        BuildDocumentsCache(sub, cache);
    }
}

static bool GetDocumentsCache(const std::wstring& documentsDir, const ScanCache*& out)
{
    std::lock_guard<std::mutex> lock(g_cacheMutex);
    auto now = std::chrono::steady_clock::now();
    if (g_cacheDir == documentsDir &&
        std::chrono::duration<double>(now - g_cacheEntry.stamp).count() < kCacheTtlSeconds)
    {
        out = &g_cacheEntry.cache;
        return true;
    }
    g_cacheDir = documentsDir;
    g_cacheEntry.stamp = now;
    g_cacheEntry.cache = ScanCache();
    BuildDocumentsCache(documentsDir, g_cacheEntry.cache);
    out = &g_cacheEntry.cache;
    return true;
}

static bool IsHardLink(const wchar_t* path, const std::wstring& documentsDir)
{
    FileInfo info;
    if (!GetInfo(path, info))
        return false;
    // Local : NumberOfLinks est fiable et ne coûte rien.
    if (info.numberOfLinks > 1)
        return true;
    // Réseau : NumberOfLinks vaut souvent 1 même pour de vrais liens durs.
    // On compare alors l'identité du fichier avec ceux de Documents/.
    const ScanCache* cache = nullptr;
    if (!GetDocumentsCache(documentsDir, cache))
        return false;
    if (info.indexHigh != 0 || info.indexLow != 0)
        return cache->exact.count(ExactKey(info)) != 0;
    // FileIndex non fourni par le serveur (fréquent en SMB) : repli sur
    // taille + horodatages (création/modification), identiques pour deux
    // noms d'un même lien dur.
    return cache->fuzzy.count(FuzzyKey(info)) != 0;
}

class DocumentLinkOverlay : public IShellIconOverlayIdentifier
{
    ULONG m_refs;
public:
    DocumentLinkOverlay() : m_refs(1) {}

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv)
    {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IShellIconOverlayIdentifier)
        {
            *ppv = static_cast<IShellIconOverlayIdentifier*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() { return InterlockedIncrement(&m_refs); }
    STDMETHODIMP_(ULONG) Release()
    {
        ULONG n = InterlockedDecrement(&m_refs);
        if (n == 0) delete this;
        return n;
    }

    // IShellIconOverlayIdentifier
    STDMETHODIMP GetPriority(int* pPriority)
    {
        if (!pPriority) return E_POINTER;
        *pPriority = 1; // valeur basse = prioritaire
        return S_OK;
    }

    // Badge les fichiers et répertoires situés sous <root>/Categories/<Catégorie>/[<Tag>/].
    // Répertoires : toute catégorie/tag est une vue virtuelle — badge direct,
    // sans test de lien dur (NumberOfLinks d'un dossier NTFS ne prouve rien).
    // Fichiers : liens durs vers <root>/Documents/, vérifiés par IDENTITÉ.
    STDMETHODIMP IsMemberOf(PCWSTR pwszPath, DWORD dwAttrib)
    {
        if (!pwszPath) return E_POINTER;
        try
        {
            std::wstring normalized(pwszPath);
            for (auto& c : normalized)
                if (c == L'/') c = L'\\';
            size_t idx = FindIgnoreCase(normalized, L"\\Categories\\");
            if (idx == std::wstring::npos)
                return S_FALSE; // pas concerné
            std::wstring rest = normalized.substr(idx + 12); // len("\Categories\")==12
            size_t first = rest.find_first_not_of(L'\\');
            if (first == std::wstring::npos)
                return S_FALSE;
            if ((dwAttrib & FILE_ATTRIBUTE_DIRECTORY) != 0 || IsDirectory(pwszPath))
                return S_OK; // vue Categories — badge direct
            std::wstring documentsDir = normalized.substr(0, idx) + L"\\Documents";
            if (IsHardLink(pwszPath, documentsDir))
                return S_OK; // afficher l'overlay
        }
        catch (...) {}
        return S_FALSE;
    }

    STDMETHODIMP GetOverlayInfo(PWSTR pwszIconFile, int cchMax, int* pIndex, DWORD* pdwFlags)
    {
        if (!pIndex || !pdwFlags) return E_POINTER;
        *pdwFlags = ISIOI_ICONFILE;
        *pIndex = 0;
        wchar_t dllPath[MAX_PATH];
        DWORD n = GetModuleFileNameW(g_hModule, dllPath, MAX_PATH);
        if (n == 0 || n >= MAX_PATH) return E_FAIL;
        std::wstring icon(dllPath, n);
        size_t slash = icon.find_last_of(L'\\');
        if (slash == std::wstring::npos) return E_FAIL;
        icon = icon.substr(0, slash + 1) + L"doclink.ico";
        if (pwszIconFile && cchMax > static_cast<int>(icon.size()))
        {
            wcscpy_s(pwszIconFile, cchMax, icon.c_str());
            return S_OK;
        }
        return E_FAIL;
    }

private:
    static size_t FindIgnoreCase(const std::wstring& hay, const wchar_t* needle)
    {
        std::wstring lower(hay);
        for (auto& c : lower)
            c = static_cast<wchar_t>(towlower(c));
        std::wstring n(needle);
        for (auto& c : n)
            c = static_cast<wchar_t>(towlower(c));
        size_t pos = lower.find(n);
        return pos;
    }
};

class OverlayClassFactory : public IClassFactory
{
    ULONG m_refs;
public:
    OverlayClassFactory() : m_refs(1) {}

    STDMETHODIMP QueryInterface(REFIID riid, void** ppv)
    {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IClassFactory)
        {
            *ppv = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() { return InterlockedIncrement(&m_refs); }
    STDMETHODIMP_(ULONG) Release()
    {
        ULONG n = InterlockedDecrement(&m_refs);
        if (n == 0) delete this;
        return n;
    }

    STDMETHODIMP CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppv)
    {
        if (!ppv) return E_POINTER;
        if (pUnkOuter) return CLASS_E_NOAGGREGATION;
        *ppv = nullptr;
        auto* obj = new(std::nothrow) DocumentLinkOverlay();
        if (!obj) return E_OUTOFMEMORY;
        HRESULT hr = obj->QueryInterface(riid, ppv);
        obj->Release();
        return hr;
    }

    STDMETHODIMP LockServer(BOOL) { return S_OK; }
};

extern "C" STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv)
{
    if (!ppv) return E_POINTER;
    if (rclsid != CLSID_DocumentLinkOverlay) return CLASS_E_CLASSNOTAVAILABLE;
    auto* factory = new(std::nothrow) OverlayClassFactory();
    if (!factory) return E_OUTOFMEMORY;
    HRESULT hr = factory->QueryInterface(riid, ppv);
    factory->Release();
    return hr;
}

extern "C" STDAPI DllCanUnloadNow()
{
    return S_FALSE; // rester chargé : le cache de Documents/ est coûteux à reconstruire
}

extern "C" BOOL WINAPI DllMain(HMODULE hModule, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        g_hModule = hModule;
        DisableThreadLibraryCalls(hModule);
    }
    return TRUE;
}
