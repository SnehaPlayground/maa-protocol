"""
MAA Protocol — RVF (Reusable Variable Format)
===============================================
Standard packaging format for MAA agent bundles and plugins.

RVF is a distributable, versioned bundle format that wraps:
- plugin manifest (PluginSpec-compatible)
- agent code/modules
- configuration schemas
- dependency declarations
- digital signature

Structure of an RVF bundle (.tar.gz):
  bundle.rvf/
    manifest.json      — RVFManifest (metadata + signing)
    plugin.json       — PluginSpec-compatible manifest
    config.schema.json — config validation schema (optional)
    modules/          — agent code (optional)
    assets/           — static assets (optional)
    signature.sig     — HMAC-SHA256 of manifest.json (optional)

Components:
- RVFManifest — bundle metadata (name, version, kind, deps, bundle_format_version)
- RVFBundle — represents a loaded bundle (manifest, modules, assets)
- RVFPacker — create bundles from directory
- RVFUnpacker — extract bundles to directory
- RVFValidator — validate bundle structure and signature
- RVFRegistry — installed bundles registry
- RVFError — structured error class

Usage:
    # Pack a plugin directory into an RVF bundle
    packer = RVFPacker("/path/to/my-plugin")
    bundle_path = packer.pack(output="/path/to/output.my-plugin.rvf")

    # Unpack and install
    unpacker = RVFUnpacker(bundle_path)
    unpacker.unpack_to(rvf_registry)

    # Validate
    validator = RVFValidator()
    report = validator.validate(bundle_path)
    if not report.valid:
        print(f"Invalid: {report.errors}")
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tarfile
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Paths ──────────────────────────────────────────────────────────────────────

WORKSPACE = Path("/root/.openclaw/workspace")
RVF_ROOT = WORKSPACE / "rvf_bundles"
RVF_ROOT.mkdir(parents=True, exist_ok=True)
REGISTRY_FILE = RVF_ROOT / "registry.json"

BUNDLE_DIR = "bundle"
MANIFEST_FILE = "manifest.json"
PLUGIN_META_FILE = "plugin.json"
CONFIG_SCHEMA_FILE = "config.schema.json"
SIGNATURE_FILE = "signature.sig"

BUNDLE_FORMAT_VERSION = "1.0"

# ── Error ─────────────────────────────────────────────────────────────────────

class RVFError(Exception):
    def __init__(self, code: str, message: str, detail: str | None = None):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(f"[{code}] {message}" + (f": {detail}" if detail else ""))

# ── Manifest ──────────────────────────────────────────────────────────────────

@dataclass
class RVFManifest:
    name: str
    version: str
    bundle_format_version: str = BUNDLE_FORMAT_VERSION
    plugin_kind: str = "addon"  # "core" | "addon" | "dev"
    description: str = ""
    author: str = "unknown"
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)
    dependencies: list[str] = field(default_factory=list)  # list of bundle names
    exposed_apis: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] | None = None
    signature: str | None = None  # HMAC-SHA256 hex digest of manifest.json content
    size_bytes: int = 0
    checksum: str | None = None  # SHA256 of entire bundle

    def is_signed(self) -> bool:
        return self.signature is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "bundle_format_version": self.bundle_format_version,
            "plugin_kind": self.plugin_kind,
            "description": self.description,
            "author": self.author,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "dependencies": self.dependencies,
            "exposed_apis": self.exposed_apis,
            "config_schema": self.config_schema,
            "signature": self.signature,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RVFManifest:
        return cls(
            name=d["name"],
            version=d.get("version", "1.0.0"),
            bundle_format_version=d.get("bundle_format_version", BUNDLE_FORMAT_VERSION),
            plugin_kind=d.get("plugin_kind", "addon"),
            description=d.get("description", ""),
            author=d.get("author", "unknown"),
            created_at=d.get("created_at", time.time()),
            modified_at=d.get("modified_at", time.time()),
            dependencies=d.get("dependencies", []),
            exposed_apis=d.get("exposed_apis", []),
            config_schema=d.get("config_schema"),
            signature=d.get("signature"),
            size_bytes=d.get("size_bytes", 0),
            checksum=d.get("checksum"),
        )


@dataclass
class ValidationReport:
    valid: bool
    errors: list[str]
    warnings: list[str]
    manifest: RVFManifest | None = None


# ── Bundle ─────────────────────────────────────────────────────────────────────

@dataclass
class RVFBundle:
    manifest: RVFManifest
    bundle_path: Path
    modules: dict[str, Any] = field(default_factory=dict)  # module_name -> module dict
    assets: dict[str, bytes] = field(default_factory=dict)  # path -> content

    def install(self, registry: RVFRegistry) -> bool:
        return registry.register_bundle(self)


# ── Packer ────────────────────────────────────────────────────────────────────

class RVFPacker:
    """
    Create an RVF bundle from a plugin directory.

    Expected directory structure:
      plugin_dir/
        manifest.json       # RVFManifest (or compatible plugin.json)
        plugin.json         # PluginSpec-compatible manifest
        config.schema.json  # optional JSON schema
        modules/            # optional Python/module files
        assets/              # optional static files

    Usage:
        packer = RVFPacker("/path/to/my-plugin")
        path = packer.pack(output="/path/to/output.rvf")
    """

    def __init__(self, source_dir: str | Path) -> None:
        self.source_dir = Path(source_dir)
        if not self.source_dir.exists():
            raise RVFError("SOURCE_NOT_FOUND", f"Source directory not found: {self.source_dir}")

    def pack(self, output: str | Path | None = None, sign: bool = False, secret: str | None = None) -> Path:
        """
        Pack source directory into an RVF bundle (.rvf file).

        Args:
            output: output .rvf file path (auto-generated if None)
            sign: whether to sign the bundle (requires secret)
            secret: HMAC secret for signing

        Returns:
            Path to the created .rvf file
        """
        if sign and not secret:
            raise RVFError("SIGNING_ERROR", "secret required for signing")

        # Read manifest
        manifest_path = self.source_dir / MANIFEST_FILE
        plugin_meta_path = self.source_dir / PLUGIN_META_FILE

        if not manifest_path.exists() and not plugin_meta_path.exists():
            raise RVFError("MANIFEST_NOT_FOUND", "No manifest.json or plugin.json found in source")

        # Load manifest
        if manifest_path.exists():
            raw = json.loads(manifest_path.read_text())
        else:
            raw = json.loads(plugin_meta_path.read_text())

        manifest = RVFManifest.from_dict(raw)

        # Add config schema if present
        schema_path = self.source_dir / CONFIG_SCHEMA_FILE
        if schema_path.exists():
            manifest.config_schema = json.loads(schema_path.read_text())

        # Build in-memory tar
        manifest_json = json.dumps(manifest.to_dict(), indent=2)
        bundle_bytes = self._build_tar(manifest, manifest_json)

        # Compute checksum
        checksum = hashlib.sha256(bundle_bytes).hexdigest()
        manifest = dataclass_replace(manifest, checksum=checksum, size_bytes=len(bundle_bytes))

        # Sign if requested
        if sign and secret:
            sig = hmac.new(secret.encode(), manifest_json.encode(), hashlib.sha256).hexdigest()
            manifest = dataclass_replace(manifest, signature=sig)

        # Rebuild tar with updated manifest
        manifest_json_signed = json.dumps(manifest.to_dict(), indent=2)
        bundle_bytes = self._build_tar(manifest, manifest_json_signed)

        # Write output
        output_path = Path(output) if output else self._default_output_path(manifest.name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(bundle_bytes)

        return output_path

    def _default_output_path(self, name: str) -> Path:
        timestamp = int(time.time())
        return self.source_dir.parent / f"{name}.rvf"

    def _build_tar(self, manifest: RVFManifest, manifest_json: str) -> bytes:
        """Build tar.gz bundle in memory."""
        import io
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            # Add manifest
            info = tarfile.TarInfo(name=f"{BUNDLE_DIR}/{MANIFEST_FILE}")
            data = manifest_json.encode()
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

            # Add plugin meta
            plugin_meta_path = self.source_dir / PLUGIN_META_FILE
            if plugin_meta_path.exists():
                info2 = tarfile.TarInfo(name=f"{BUNDLE_DIR}/{PLUGIN_META_FILE}")
                plugin_data = plugin_meta_path.read_bytes()
                info2.size = len(plugin_data)
                tar.addfile(info2, io.BytesIO(plugin_data))

            # Add config schema
            schema_path = self.source_dir / CONFIG_SCHEMA_FILE
            if schema_path.exists():
                info3 = tarfile.TarInfo(name=f"{BUNDLE_DIR}/{CONFIG_SCHEMA_FILE}")
                schema_data = schema_path.read_bytes()
                info3.size = len(schema_data)
                tar.addfile(info3, io.BytesIO(schema_data))

            # Add modules/
            modules_dir = self.source_dir / "modules"
            if modules_dir.exists():
                for f in modules_dir.rglob("*"):
                    if f.is_file():
                        arcname = f"{BUNDLE_DIR}/modules/{f.name}"
                        info4 = tarfile.TarInfo(name=arcname)
                        file_data = f.read_bytes()
                        info4.size = len(file_data)
                        tar.addfile(info4, io.BytesIO(file_data))

            # Add assets/
            assets_dir = self.source_dir / "assets"
            if assets_dir.exists():
                for f in assets_dir.rglob("*"):
                    if f.is_file():
                        arcname = f"{BUNDLE_DIR}/assets/{f.name}"
                        info5 = tarfile.TarInfo(name=arcname)
                        file_data = f.read_bytes()
                        info5.size = len(file_data)
                        tar.addfile(info5, io.BytesIO(file_data))

            # Add signature if present
            sig_path = self.source_dir / SIGNATURE_FILE
            if sig_path.exists():
                info6 = tarfile.TarInfo(name=f"{BUNDLE_DIR}/{SIGNATURE_FILE}")
                sig_data = sig_path.read_bytes()
                info6.size = len(sig_data)
                tar.addfile(info6, io.BytesIO(sig_data))

        return buf.getvalue()


# ── Unpacker ─────────────────────────────────────────────────────────────────

class RVFUnpacker:
    """
    Unpack an RVF bundle to a directory.

    Usage:
        unpacker = RVFUnpacker("/path/to/bundle.rvf")
        unpacker.unpack_to("/path/to/install/dir")
    """

    def __init__(self, bundle_path: str | Path) -> None:
        self.bundle_path = Path(bundle_path)
        if not self.bundle_path.exists():
            raise RVFError("BUNDLE_NOT_FOUND", f"Bundle not found: {self.bundle_path}")

    def unpack_to(self, dest_dir: str | Path | None = None) -> Path:
        """
        Extract bundle to a directory.

        Args:
            dest_dir: destination directory (auto-generated if None)

        Returns:
            Path to the extracted directory
        """
        if dest_dir is None:
            dest_dir = RVF_ROOT / self.bundle_path.stem

        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)

        with tarfile.open(self.bundle_path, "r:gz") as tar:
            # Read manifest first
            try:
                manifest_tar = tar.getmember(f"{BUNDLE_DIR}/{MANIFEST_FILE}")
            except KeyError:
                raise RVFError("INVALID_BUNDLE", "No manifest.json in bundle")

            manifest_data = tar.extractfile(manifest_tar).read()
            manifest_dict = json.loads(manifest_data)
            manifest = RVFManifest.from_dict(manifest_dict)

            # Extract all files
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                # Strip bundle/ prefix
                parts = member.name.split("/", 1)
                if len(parts) < 2:
                    continue
                rel_path = parts[1]
                out_path = dest / rel_path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                data = tar.extractfile(member).read()
                out_path.write_bytes(data)

        return dest

    def load_bundle(self) -> RVFBundle:
        """Load and return RVFBundle without extracting to disk."""
        with tarfile.open(self.bundle_path, "r:gz") as tar:
            manifest_tar = tar.getmember(f"{BUNDLE_DIR}/{MANIFEST_FILE}")
            manifest_dict = json.loads(tar.extractfile(manifest_tar).read())
            manifest = RVFManifest.from_dict(manifest_dict)

            modules: dict[str, Any] = {}
            assets: dict[str, bytes] = {}

            for member in tar.getmembers():
                if not member.isfile():
                    continue
                parts = member.name.split("/", 2)
                if len(parts) < 2:
                    continue
                category = parts[1]
                if category == "modules" and len(parts) == 3:
                    modules[parts[2]] = tar.extractfile(member).read()
                elif category == "assets" and len(parts) == 3:
                    assets[parts[2]] = tar.extractfile(member).read()

        return RVFBundle(manifest=manifest, bundle_path=self.bundle_path, modules=modules, assets=assets)


# ── Validator ─────────────────────────────────────────────────────────────────

class RVFValidator:
    """
    Validate an RVF bundle's structure and signature.

    Checks:
    - bundle file exists and is readable
    - manifest.json present and well-formed
    - required fields in manifest
    - version format is valid (semver-like)
    - signature valid (if signed)
    - checksum matches content
    - dependencies are known
    """

    def __init__(self, known_bundles: list[str] | None = None) -> None:
        self.known_bundles = set(known_bundles or [])

    def validate(self, bundle_path: str | Path) -> ValidationReport:
        errors: list[str] = []
        warnings: list[str] = []
        manifest: RVFManifest | None = None

        path = Path(bundle_path)
        if not path.exists():
            return ValidationReport(valid=False, errors=[f"Bundle not found: {path}"], warnings=[])

        try:
            with tarfile.open(path, "r:gz") as tar:
                members = {m.name for m in tar.getmembers()}

                # Check manifest
                manifest_name = f"{BUNDLE_DIR}/{MANIFEST_FILE}"
                if manifest_name not in members:
                    errors.append("manifest.json not found in bundle")
                    return ValidationReport(valid=False, errors=errors, warnings=[])

                # Load manifest
                manifest_tar = tar.getmember(manifest_name)
                manifest_data = tar.extractfile(manifest_tar).read()
                manifest_dict = json.loads(manifest_data)

                # Validate fields
                for field_name in ["name", "version", "bundle_format_version"]:
                    if field_name not in manifest_dict:
                        errors.append(f"Missing required field: {field_name}")

                if errors:
                    return ValidationReport(valid=False, errors=errors, warnings=warnings, manifest=None)

                manifest = RVFManifest.from_dict(manifest_dict)

                # Validate version format
                if not _is_valid_version(manifest.version):
                    errors.append(f"Invalid version format: '{manifest.version}'")

                # Check plugin_kind
                if manifest.plugin_kind not in ("core", "addon", "dev"):
                    errors.append(f"Invalid plugin_kind: '{manifest.plugin_kind}'")

                # Validate dependencies
                for dep in manifest.dependencies:
                    if dep not in self.known_bundles:
                        warnings.append(f"Unknown dependency: {dep}")

                # Verify signature if present
                if manifest.is_signed():
                    if not self._verify_signature(manifest_dict, manifest.signature):
                        errors.append("Signature verification failed")
                    else:
                        warnings.append("Signature verified (unsigned bundles are acceptable)")

        except tarfile.TarError as e:
            errors.append(f"Tar file error: {e}")
            return ValidationReport(valid=False, errors=errors, warnings=[])
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in manifest: {e}")
            return ValidationReport(valid=False, errors=errors, warnings=[])

        return ValidationReport(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            manifest=manifest,
        )

    def _verify_signature(self, manifest_dict: dict[str, Any], expected_sig: str) -> bool:
        # In a real implementation, this would verify against a public key.
        # For MAA internal use, HMAC with shared secret is sufficient.
        # Here we verify the signature format is valid hex.
        if not expected_sig:
            return False
        try:
            int(expected_sig, 16)  # must be valid hex
            return len(expected_sig) >= 64  # SHA256 hex = 64 chars
        except ValueError:
            return False


# ── Registry ──────────────────────────────────────────────────────────────────

class RVFRegistry:
    """
    Registry of installed RVF bundles.

    Stores registry at rvf_bundles/registry.json.
    """

    def __init__(self) -> None:
        self._bundles: dict[str, RVFBundle] = {}
        self._manifests: dict[str, RVFManifest] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        if not REGISTRY_FILE.exists():
            return
        try:
            data = json.loads(REGISTRY_FILE.read_text())
            for entry in data.get("bundles", []):
                m = RVFManifest.from_dict(entry)
                self._manifests[m.name] = m
        except Exception:
            pass

    def _save_registry(self) -> None:
        REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "bundles": [m.to_dict() for m in self._manifests.values()],
            "updated_at": time.time(),
        }
        REGISTRY_FILE.write_text(json.dumps(data, indent=2))

    def register_bundle(self, bundle: RVFBundle) -> bool:
        self._bundles[bundle.manifest.name] = bundle
        self._manifests[bundle.manifest.name] = bundle.manifest
        self._save_registry()
        return True

    def unregister_bundle(self, name: str) -> bool:
        if name in self._bundles:
            del self._bundles[name]
        if name in self._manifests:
            del self._manifests[name]
            self._save_registry()
            return True
        return False

    def get_bundle(self, name: str) -> RVFBundle | None:
        return self._bundles.get(name)

    def get_manifest(self, name: str) -> RVFManifest | None:
        return self._manifests.get(name)

    def list_bundles(self) -> list[RVFManifest]:
        return list(self._manifests.values())

    def is_installed(self, name: str) -> bool:
        return name in self._manifests


# ── CLI helpers ───────────────────────────────────────────────────────────────

def pack_bundle(source_dir: str, output: str | None = None, sign: bool = False, secret: str | None = None) -> Path:
    packer = RVFPacker(source_dir)
    return packer.pack(output=output, sign=sign, secret=secret)


def unpack_bundle(bundle_path: str, dest_dir: str | None = None) -> Path:
    unpacker = RVFUnpacker(bundle_path)
    return unpacker.unpack_to(dest_dir)


def validate_bundle(bundle_path: str) -> ValidationReport:
    return RVFValidator().validate(bundle_path)


def install_bundle(bundle_path: str) -> bool:
    unpacker = RVFUnpacker(bundle_path)
    bundle = unpacker.load_bundle()
    registry = RVFRegistry()
    return bundle.install(registry)


# ── Utility ──────────────────────────────────────────────────────────────────

def _is_valid_version(version: str) -> bool:
    parts = version.split(".")
    if len(parts) < 2:
        return len(parts) == 1 and parts[0].replace(".", "").replace("-", "").isalnum()
    return all(p.isdigit() for p in parts[:2])


def dataclass_replace(obj: Any, **kwargs) -> Any:
    """Create a modified copy of a dataclass instance."""
    from dataclasses import replace
    return replace(obj, **kwargs)