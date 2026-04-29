"""RVF bundle format support."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import tarfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

RVF_ROOT = Path('/tmp/maa-x-rvf')
RVF_ROOT.mkdir(parents=True, exist_ok=True)
REGISTRY_FILE = RVF_ROOT / 'registry.json'
BUNDLE_DIR = 'bundle'
MANIFEST_FILE = 'manifest.json'
PLUGIN_META_FILE = 'plugin.json'
CONFIG_SCHEMA_FILE = 'config.schema.json'
SIGNATURE_FILE = 'signature.sig'
BUNDLE_FORMAT_VERSION = '1.0'


class RVFError(Exception):
    def __init__(self, code: str, message: str, detail: str | None = None):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(f'[{code}] {message}' + (f': {detail}' if detail else ''))


@dataclass
class RVFManifest:
    name: str
    version: str
    bundle_format_version: str = BUNDLE_FORMAT_VERSION
    plugin_kind: str = 'addon'
    description: str = ''
    author: str = 'unknown'
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)
    dependencies: list[str] = field(default_factory=list)
    exposed_apis: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] | None = None
    signature: str | None = None
    size_bytes: int = 0
    checksum: str | None = None

    def is_signed(self) -> bool:
        return self.signature is not None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'RVFManifest':
        return cls(
            name=d['name'],
            version=d.get('version', '1.0.0'),
            bundle_format_version=d.get('bundle_format_version', BUNDLE_FORMAT_VERSION),
            plugin_kind=d.get('plugin_kind', 'addon'),
            description=d.get('description', ''),
            author=d.get('author', 'unknown'),
            created_at=d.get('created_at', time.time()),
            modified_at=d.get('modified_at', time.time()),
            dependencies=d.get('dependencies', []),
            exposed_apis=d.get('exposed_apis', []),
            config_schema=d.get('config_schema'),
            signature=d.get('signature'),
            size_bytes=d.get('size_bytes', 0),
            checksum=d.get('checksum'),
        )


@dataclass
class ValidationReport:
    valid: bool
    errors: list[str]
    warnings: list[str]
    manifest: RVFManifest | None = None


@dataclass
class RVFBundle:
    manifest: RVFManifest
    bundle_path: Path
    modules: dict[str, Any] = field(default_factory=dict)
    assets: dict[str, bytes] = field(default_factory=dict)

    def install(self, registry: 'RVFRegistry') -> bool:
        return registry.register_bundle(self)


class RVFPacker:
    def __init__(self, source_dir: str | Path) -> None:
        self.source_dir = Path(source_dir)
        if not self.source_dir.exists():
            raise RVFError('SOURCE_NOT_FOUND', f'Source directory not found: {self.source_dir}')

    def pack(self, output: str | Path | None = None, sign: bool = False, secret: str | None = None) -> Path:
        if sign and not secret:
            raise RVFError('SIGNING_ERROR', 'secret required for signing')
        manifest_path = self.source_dir / MANIFEST_FILE
        plugin_meta_path = self.source_dir / PLUGIN_META_FILE
        if not manifest_path.exists() and not plugin_meta_path.exists():
            raise RVFError('MANIFEST_NOT_FOUND', 'No manifest.json or plugin.json found in source')
        raw = json.loads((manifest_path if manifest_path.exists() else plugin_meta_path).read_text())
        manifest = RVFManifest.from_dict(raw)
        schema_path = self.source_dir / CONFIG_SCHEMA_FILE
        if schema_path.exists():
            manifest.config_schema = json.loads(schema_path.read_text())
        manifest_json = json.dumps(manifest.to_dict(), indent=2)
        bundle_bytes = self._build_tar(manifest_json)
        manifest = replace(manifest, checksum=hashlib.sha256(bundle_bytes).hexdigest(), size_bytes=len(bundle_bytes))
        if sign and secret:
            manifest = replace(manifest, signature=hmac.new(secret.encode(), json.dumps(manifest.to_dict(), sort_keys=True).encode(), hashlib.sha256).hexdigest())
        bundle_bytes = self._build_tar(json.dumps(manifest.to_dict(), indent=2))
        output_path = Path(output) if output else self.source_dir.parent / f'{manifest.name}.rvf'
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(bundle_bytes)
        return output_path

    def _build_tar(self, manifest_json: str) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            def add_bytes(name: str, data: bytes):
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            add_bytes(f'{BUNDLE_DIR}/{MANIFEST_FILE}', manifest_json.encode())
            for rel in (PLUGIN_META_FILE, CONFIG_SCHEMA_FILE):
                p = self.source_dir / rel
                if p.exists():
                    add_bytes(f'{BUNDLE_DIR}/{rel}', p.read_bytes())
            for folder in ('modules', 'assets'):
                d = self.source_dir / folder
                if d.exists():
                    for f in d.rglob('*'):
                        if f.is_file():
                            add_bytes(f'{BUNDLE_DIR}/{folder}/{f.name}', f.read_bytes())
        return buf.getvalue()


class RVFUnpacker:
    def __init__(self, bundle_path: str | Path) -> None:
        self.bundle_path = Path(bundle_path)
        if not self.bundle_path.exists():
            raise RVFError('BUNDLE_NOT_FOUND', f'Bundle not found: {self.bundle_path}')

    def unpack_to(self, dest_dir: str | Path | None = None) -> Path:
        dest = Path(dest_dir) if dest_dir else RVF_ROOT / self.bundle_path.stem
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(self.bundle_path, 'r:gz') as tar:
            for member in tar.getmembers():
                if member.isfile():
                    parts = member.name.split('/', 1)
                    if len(parts) == 2:
                        out_path = dest / parts[1]
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_bytes(tar.extractfile(member).read())
        return dest

    def load_bundle(self) -> RVFBundle:
        with tarfile.open(self.bundle_path, 'r:gz') as tar:
            manifest = RVFManifest.from_dict(json.loads(tar.extractfile(tar.getmember(f'{BUNDLE_DIR}/{MANIFEST_FILE}')).read()))
            modules, assets = {}, {}
            for member in tar.getmembers():
                if member.isfile():
                    parts = member.name.split('/', 2)
                    if len(parts) == 3 and parts[1] == 'modules':
                        modules[parts[2]] = tar.extractfile(member).read()
                    elif len(parts) == 3 and parts[1] == 'assets':
                        assets[parts[2]] = tar.extractfile(member).read()
            return RVFBundle(manifest, self.bundle_path, modules, assets)


class RVFValidator:
    def __init__(self, known_bundles: list[str] | None = None) -> None:
        self.known_bundles = set(known_bundles or [])

    def validate(self, bundle_path: str | Path) -> ValidationReport:
        path = Path(bundle_path)
        if not path.exists():
            return ValidationReport(False, [f'Bundle not found: {path}'], [])
        errors, warnings = [], []
        manifest = None
        try:
            with tarfile.open(path, 'r:gz') as tar:
                names = {m.name for m in tar.getmembers()}
                manifest_name = f'{BUNDLE_DIR}/{MANIFEST_FILE}'
                if manifest_name not in names:
                    return ValidationReport(False, ['manifest.json not found in bundle'], [])
                manifest = RVFManifest.from_dict(json.loads(tar.extractfile(tar.getmember(manifest_name)).read()))
                if not manifest.name or not manifest.version:
                    errors.append('Missing required fields')
                for dep in manifest.dependencies:
                    if dep not in self.known_bundles:
                        warnings.append(f'Unknown dependency: {dep}')
                if manifest.signature:
                    try:
                        int(manifest.signature, 16)
                        if len(manifest.signature) < 64:
                            errors.append('Signature verification failed')
                    except ValueError:
                        errors.append('Signature verification failed')
        except Exception as e:
            errors.append(str(e))
        return ValidationReport(len(errors) == 0, errors, warnings, manifest)


class RVFRegistry:
    def __init__(self) -> None:
        self._bundles: dict[str, RVFBundle] = {}
        self._manifests: dict[str, RVFManifest] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        if REGISTRY_FILE.exists():
            try:
                data = json.loads(REGISTRY_FILE.read_text())
                for entry in data.get('bundles', []):
                    m = RVFManifest.from_dict(entry)
                    self._manifests[m.name] = m
            except Exception:
                pass

    def _save_registry(self) -> None:
        REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        REGISTRY_FILE.write_text(json.dumps({'bundles': [m.to_dict() for m in self._manifests.values()], 'updated_at': time.time()}, indent=2))

    def register_bundle(self, bundle: RVFBundle) -> bool:
        self._bundles[bundle.manifest.name] = bundle
        self._manifests[bundle.manifest.name] = bundle.manifest
        self._save_registry()
        return True

    def unregister_bundle(self, name: str) -> bool:
        self._bundles.pop(name, None)
        existed = name in self._manifests
        self._manifests.pop(name, None)
        if existed:
            self._save_registry()
        return existed

    def get_bundle(self, name: str) -> RVFBundle | None:
        return self._bundles.get(name)

    def get_manifest(self, name: str) -> RVFManifest | None:
        return self._manifests.get(name)

    def list_bundles(self) -> list[RVFManifest]:
        return list(self._manifests.values())

    def is_installed(self, name: str) -> bool:
        return name in self._manifests


def pack_bundle(source_dir: str, output: str | None = None, sign: bool = False, secret: str | None = None) -> Path:
    return RVFPacker(source_dir).pack(output=output, sign=sign, secret=secret)


def unpack_bundle(bundle_path: str, dest_dir: str | None = None) -> Path:
    return RVFUnpacker(bundle_path).unpack_to(dest_dir)


def validate_bundle(bundle_path: str) -> ValidationReport:
    return RVFValidator().validate(bundle_path)


def install_bundle(bundle_path: str) -> bool:
    bundle = RVFUnpacker(bundle_path).load_bundle()
    return bundle.install(RVFRegistry())
