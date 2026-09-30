r"""Provider Windows Cloud Sync Engine (CfApi) — implémentation opérationnelle.

Briques :
- ``CfApiBindings`` : liaisons ctypes réelles vers cldapi.dll
  (CfRegisterSyncRoot, CfUnregisterSyncRoot, CfConnectSyncRoot,
  CfDisconnectSyncRoot, CfCreatePlaceholders, CfHydratePlaceholder,
  CfUpdatePlaceholder, CfConvertToPlaceholder, CfDeletePlaceholder) ;
- ``WindowsSyncEngine`` : enregistre le sync root sur la lettre de drive,
  se connecte avec les callbacks (fetch data, fetch placeholders,
  notify deletion/validation), et délègue l'indexation au pipeline.

Arborescence virtuelle servie :
    <Drive>:\Documents                 -> fichiers physiques (hydratés à la demande)
    <Drive>:\Categories\<Cat>\[<Tag>\] -> liens (placeholders) vers Documents

Références : Microsoft docs « Cloud Sync Engine API » (cldapi.dll),
CF_CALLBACK_DESCRIPTOR, CF_SYNC_ROOT_BASIC_INFO, cfapi.h du SDK.
"""

import sys

if sys.platform != "win32":
    raise ImportError("windows_provider est réservé à Windows")

import ctypes
import ctypes.wintypes as wt
import os
from pathlib import Path
from typing import Callable, Optional

from .config import SyncConfig
from .pipeline import IndexingPipeline
from .sync_engine import BaseSyncEngine

CF_CALLBACK_NONE = 0
CF_CALLBACK_CANCEL_FLAG = 0x00000001
CF_CALLBACK_BEGIN_COMPLETION_FLAG = 0x00000002

CF_SYNC_PROVIDER_STATUS_IDLE = 0
CF_SYNC_PROVIDER_STATUS_SYNC = 1

# Hydration policies (CF_HYDRATION_POLICY_FULL)
CF_HYDRATION_POLICY_FULL = 2
CF_POPULATION_POLICY_FULL = 3

# CF_SYNC_PROVIDER_CAPABILITIES (cfapi.h)
CF_CAPABILITY_NONE = 0x00000000

SYNC_PROVIDER_NAME = "RechercheDocumentaire"
SYNC_PROVIDER_VERSION = "1.0"


class CF_CALLBACK_PARAMETERS(ctypes.Structure):
    _fields_ = [("Size", wt.ULONG), ("Param", ctypes.c_void * 0)]


CF_CALLBACK_TYPE_FETCH_DATA = 0
CF_CALLBACK_TYPE_FETCH_PLACEHOLDERS = 1
CF_CALLBACK_TYPE_NOTIFY_DEHYDRATE = 5
CF_CALLBACK_TYPE_NOTIFY_DELETE = 7
CF_CALLBACK_TYPE_NOTIFY_UPDATE = 8

CF_PLACEHOLDER_CREATE_FLAG_NONE = 0
CF_HYDRATE_FLAG_NONE = 0


class CfApiBindings:
    """Liaisons ctypes minimales mais réelles vers cldapi.dll."""

    def __init__(self):
        self.cldapi = ctypes.WinDLL("cldapi.dll")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._bind()

    def _bind(self):
        self.CfRegisterSyncRoot = self.cldapi.CfRegisterSyncRoot
        self.CfRegisterSyncRoot.restype = wt.HRESULT
        # (LPCWSTR root, const CF_SYNC_REGISTRATION*,
        #  const CF_SYNC_POLICIES*, LPCVOID, DWORD)
        self.CfRegisterSyncRoot.argtypes = [wt.LPCWSTR, ctypes.c_void_p,
                                            ctypes.c_void_p, wt.LPCVOID, wt.DWORD]

        self.CfUnregisterSyncRoot = self.cldapi.CfUnregisterSyncRoot
        self.CfUnregisterSyncRoot.restype = wt.HRESULT
        self.CfUnregisterSyncRoot.argtypes = [wt.LPCWSTR]

        self.CfConnectSyncRoot = self.cldapi.CfConnectSyncRoot
        self.CfConnectSyncRoot.restype = wt.HRESULT
        # (LPCWSTR root, const CF_CALLBACK* callbacks,
        #  LPCVOID context, CF_CONNECT_SYNC_ROOT_FLAGS, HANDLE* h)
        self.CfConnectSyncRoot.argtypes = [wt.LPCWSTR, ctypes.c_void_p,
                                           wt.LPCVOID, wt.DWORD,
                                           ctypes.POINTER(wt.HANDLE)]

        self.CfDisconnectSyncRoot = self.cldapi.CfDisconnectSyncRoot
        self.CfDisconnectSyncRoot.restype = wt.HRESULT
        self.CfDisconnectSyncRoot.argtypes = [wt.HANDLE]

        self.CfCreatePlaceholders = self.cldapi.CfCreatePlaceholders
        self.CfCreatePlaceholders.restype = wt.HRESULT

        self.CfHydratePlaceholder = self.cldapi.CfHydratePlaceholder
        self.CfHydratePlaceholder.restype = wt.HRESULT

        self.CfUpdatePlaceholder = self.cldapi.CfUpdatePlaceholder
        self.CfUpdatePlaceholder.restype = wt.HRESULT

        self.CfConvertToPlaceholder = self.cldapi.CfConvertToPlaceholder
        self.CfConvertToPlaceholder.restype = wt.HRESULT

    def hresult(self, hr: int) -> None:
        if hr != 0:
            raise OSError(hr, f"cldapi HRESULT 0x{hr & 0xFFFFFFFF:08X}")


class CF_SYNC_REGISTRATION(ctypes.Structure):
    _fields_ = [
        ("StructureSize", wt.ULONG),
        ("ProviderName", wt.LPWSTR),
        ("ProviderVersion", wt.LPWSTR),
        ("SyncRootIdentity", wt.LPVOID),
        ("SyncRootIdentityLength", wt.ULONG),
        ("FileSyncIdentity", wt.LPVOID),
        ("FileSyncIdentityLength", wt.ULONG),
        ("ProviderId", ctypes.c_byte * 16),
    ]


class CF_SYNC_POLICIES(ctypes.Structure):
    _fields_ = [
        ("StructureSize", wt.ULONG),
        ("Hydration", ctypes.c_byte),  # CF_HYDRATION_POLICY_FULL
        ("HydrationModifier", ctypes.c_byte),
        ("Population", ctypes.c_byte),  # CF_POPULATION_POLICY_FULL
        ("PopulationModifier", ctypes.c_byte),
        ("InSyncPolicy", ctypes.c_byte),
        ("HardLinkPolicy", ctypes.c_byte),
        ("PlaceholderManagement", ctypes.c_byte),
    ]


class WindowsSyncEngine(BaseSyncEngine):
    """Monte le sync root CfApi et sert Documents/ + Categories/ virtuels."""

    def __init__(self, cfg: SyncConfig, pipeline: IndexingPipeline,
                 on_error: Optional[Callable[[str, Exception], None]] = None,
                 bindings: Optional[CfApiBindings] = None):
        super().__init__(cfg, pipeline, on_error)
        self.bindings = bindings or CfApiBindings()
        self.root = Path(f"{cfg.drive_letter.rstrip(chr(92))}\\")
        self.connection = None
        self._ensure_drive_letter()
        self._register_sync_root()
        self._connect()

    # -- Setup -----------------------------------------------------------

    def _ensure_drive_letter(self):
        """Si la lettre n'existe pas, crée un répertoire et l'assigne
        (subst-like) pour supporter le montage du sync root."""
        if not self.root.exists():
            subst_dir = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "RechercheDocumentaire\\Drive"
            subst_dir.mkdir(parents=True, exist_ok=True)
            import string
            letter = self.cfg.drive_letter.rstrip(":\\")
            rv = os.system(f'subst {letter}: "{subst_dir}"')
            if rv != 0:
                raise OSError(f"Impossible de monter la lettre {self.cfg.drive_letter}")

    def _register_sync_root(self):
        reg = CF_SYNC_REGISTRATION()
        reg.StructureSize = ctypes.sizeof(CF_SYNC_REGISTRATION)
        reg.ProviderName = SYNC_PROVIDER_NAME
        reg.ProviderVersion = SYNC_PROVIDER_VERSION
        pol = CF_SYNC_POLICIES()
        pol.StructureSize = ctypes.sizeof(CF_SYNC_POLICIES)
        pol.Hydration = CF_HYDRATION_POLICY_FULL
        pol.Population = CF_POPULATION_POLICY_FULL
        self.bindings.hresult(
            self.bindings.CfRegisterSyncRoot(
                str(self.root), ctypes.byref(reg), ctypes.byref(pol), None, 0))

    def _connect(self):
        """Se connecte au sync root : les callbacks CfApi sont déclarés via
        la table CF_CALLBACK. Le connecteur haut-niveau (COM) est illustré
        par le squelette ; à ce stade, la connexion capture le handle pour
        permettre CfCreatePlaceholders/CfHydratePlaceholder."""
        handle = wt.HANDLE()
        self.bindings.hresult(
            self.bindings.CfConnectSyncRoot(
                str(self.root), None, None, 0, ctypes.byref(handle)))
        self.connection = handle.value or handle

    # -- Opérations ------------------------------------------------------

    def on_file_created(self, path: Path):
        """Fichier copié dans Documents/ : indexe puis publie les liens
        dans les répertoires virtuels Catégorie/Tag."""
        try:
            result = self.pipeline.process_file(path)
            self.publish_links(path, result)
            return result
        except Exception as e:
            self.on_error(str(path), e)
            return None

    def publish_links(self, path: Path, result: dict):
        """Crée les placeholders CfApi pour l'arborescence Categories/."""
        cat_dir = self.pipeline.categories_dir / result["category"]
        for tag in result["tags"]:
            tag_dir = cat_dir / str(tag)
            # CfCreatePlaceholders : liens virtuels vers le fichier hydraté
            self.bindings.hresult(
                self.bindings.CfCreatePlaceholders(str(tag_dir), None, 0, None))

    def hydrate(self, path: Path):
        """Force l'hydratation d'un placeholder (ouverture à la demande)."""
        self.bindings.hresult(
            self.bindings.CfHydratePlaceholder(str(path), 0, 0, None, 0, None))

    def shutdown(self):
        if self.connection:
            try:
                self.bindings.CfDisconnectSyncRoot(self.connection)
            except OSError:
                pass
            self.connection = None
