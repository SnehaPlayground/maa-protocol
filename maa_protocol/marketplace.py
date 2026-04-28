"""
MAA Protocol — Plugin Marketplace
===================================
Internal plugin discovery, listing, and distribution registry.

Provides a searchable marketplace for MAA plugins:
- PluginStore — searchable registry of available plugins
- MarketplaceCatalog — aggregated catalog with categories, ratings, versions
- Listing — plugin listing with metadata, compatibility, dependencies
- MarketplaceError — structured error class

This is NOT a public distribution platform. It's an internal tool for
MAA operators to discover, evaluate, and manage plugin availability.

Components:
- PluginStore — CRUD operations for plugin listings
- MarketplaceCatalog — aggregated catalog with search/filter
- Listing — individual plugin listing with full metadata
- PluginIndexer — builds and maintains search index
- ReviewSystem — ratings and reviews for plugins

Usage:
    store = PluginStore()
    listing = store.create_listing(name="my-plugin", version="1.0.0", category="research")
    results = store.search("market research")
    catalog = store.get_catalog()
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WORKSPACE = Path("/root/.openclaw/workspace")
MARKETPLACE_DIR = WORKSPACE / "maa_protocol" / "marketplace"
MARKETPLACE_DIR.mkdir(parents=True, exist_ok=True)
LISTINGS_DIR = MARKETPLACE_DIR / "listings"
LISTINGS_DIR.mkdir(parents=True, exist_ok=True)
INDEX_FILE = MARKETPLACE_DIR / "index.json"
CATALOG_FILE = MARKETPLACE_DIR / "catalog.json"


# ── Errors ───────────────────────────────────────────────────────────────────

class MarketplaceError(Exception):
    def __init__(self, code: str, message: str, detail: str | None = None):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(f"[{code}] {message}" + (f": {detail}" if detail else ""))


# ── Listing ──────────────────────────────────────────────────────────────────

@dataclass
class Listing:
    id: str
    name: str
    version: str
    category: str
    description: str
    author: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    compatibility: list[str] = field(default_factory=list)  # MAA version compat
    bundle_path: str | None = None
    bundle_size_bytes: int = 0
    downloads: int = 0
    rating: float = 0.0
    rating_count: int = 0
    reviews: list[Review] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    installed: bool = False
    enabled: bool = False
    status: str = "active"  # active | deprecated | hidden

    def is_compatible(self, maa_version: str) -> bool:
        if not self.compatibility:
            return True
        return maa_version in self.compatibility or "any" in self.compatibility

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "category": self.category,
            "description": self.description,
            "author": self.author,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "compatibility": self.compatibility,
            "bundle_path": self.bundle_path,
            "bundle_size_bytes": self.bundle_size_bytes,
            "downloads": self.downloads,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "dependencies": self.dependencies,
            "installed": self.installed,
            "enabled": self.enabled,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Listing:
        reviews = [Review.from_dict(r) for r in d.get("reviews", [])]
        obj = cls(
            id=d["id"], name=d["name"], version=d["version"],
            category=d["category"], description=d["description"],
            author=d["author"], created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            tags=d.get("tags", []), compatibility=d.get("compatibility", []),
            bundle_path=d.get("bundle_path"), bundle_size_bytes=d.get("bundle_size_bytes", 0),
            downloads=d.get("downloads", 0), rating=d.get("rating", 0.0),
            rating_count=d.get("rating_count", 0), reviews=reviews,
            dependencies=d.get("dependencies", []),
            installed=d.get("installed", False), enabled=d.get("enabled", False),
            status=d.get("status", "active"),
        )
        return obj


@dataclass
class Review:
    id: str
    author: str
    rating: int  # 1-5
    title: str
    body: str
    created_at: float = field(default_factory=time.time)
    helpful: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "author": self.author, "rating": self.rating,
            "title": self.title, "body": self.body,
            "created_at": self.created_at, "helpful": self.helpful,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Review:
        return cls(**d)


# ── PluginIndexer ────────────────────────────────────────────────────────────

class PluginIndexer:
    """
    Search index for plugin listings.

    Maintains a simple inverted index over plugin names, descriptions, tags.

    Usage:
        indexer = PluginIndexer()
        indexer.index(listing)
        results = indexer.search("market research")
    """

    def __init__(self) -> None:
        self._term_to_ids: dict[str, set[str]] = {}
        self._listing_ids: set[str] = set()

    def index(self, listing: Listing) -> None:
        self._listing_ids.add(listing.id)
        terms = self._extract_terms(listing)
        for term in terms:
            if term not in self._term_to_ids:
                self._term_to_ids[term] = set()
            self._term_to_ids[term].add(listing.id)

    def unindex(self, listing_id: str, listing: Listing) -> None:
        self._listing_ids.discard(listing_id)
        terms = self._extract_terms(listing)
        for term in terms:
            if term in self._term_to_ids:
                self._term_to_ids[term].discard(listing_id)

    def search(self, query: str, limit: int = 20) -> list[str]:
        """Return listing IDs matching query, sorted by relevance."""
        query_terms = self._extract_terms_from_query(query)
        if not query_terms:
            return list(self._listing_ids)[:limit]

        # Score each listing by how many query terms it matches
        scores: dict[str, int] = {}
        for term in query_terms:
            for lid in self._term_to_ids.get(term, set()):
                scores[lid] = scores.get(lid, 0) + 1

        if not scores:
            return list(self._listing_ids)[:limit]

        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
        return sorted_ids[:limit]

    def _extract_terms(self, listing: Listing) -> set[str]:
        text = f"{listing.name} {listing.description} {' '.join(listing.tags)} {listing.category}"
        return set(text.lower().split())

    def _extract_terms_from_query(self, query: str) -> list[str]:
        return [t for t in query.lower().split() if len(t) >= 2]

    def to_dict(self) -> dict[str, Any]:
        return {
            "term_to_ids": {t: list(ids) for t, ids in self._term_to_ids.items()},
            "listing_ids": list(self._listing_ids),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PluginIndexer:
        indexer = cls()
        indexer._term_to_ids = {t: set(ids) for t, ids in d.get("term_to_ids", {}).items()}
        indexer._listing_ids = set(d.get("listing_ids", []))
        return indexer


# ── PluginStore ──────────────────────────────────────────────────────────────

class PluginStore:
    """
    CRUD store for plugin marketplace listings.

    Usage:
        store = PluginStore()
        store.create_listing(name="market-research", version="1.0", category="research", ...)
        results = store.search("research")
        listing = store.get("market-research")
        store.update_rating("market-research", 4.5)
    """

    def __init__(self) -> None:
        self._listings: dict[str, Listing] = {}
        self._indexer = PluginIndexer()
        self._load()

    def _load(self) -> None:
        if not LISTINGS_DIR.exists():
            return
        for f in LISTINGS_DIR.glob("*.json"):
            try:
                d = json.loads(f.read_text())
                listing = Listing.from_dict(d)
                self._listings[listing.id] = listing
                self._indexer.index(listing)
            except Exception:
                pass

    def _save(self, listing: Listing) -> None:
        LISTINGS_DIR.mkdir(parents=True, exist_ok=True)
        path = LISTINGS_DIR / f"{listing.id}.json"
        path.write_text(json.dumps(listing.to_dict(), indent=2))

    def _make_id(self, name: str) -> str:
        return hashlib.sha256(name.encode()).hexdigest()[:16]

    def create_listing(
        self,
        name: str,
        version: str,
        category: str,
        description: str = "",
        author: str = "unknown",
        tags: list[str] | None = None,
        compatibility: list[str] | None = None,
        bundle_path: str | None = None,
        dependencies: list[str] | None = None,
    ) -> Listing:
        listing_id = self._make_id(f"{name}:{version}")
        if listing_id in self._listings:
            raise MarketplaceError("DUPLICATE_LISTING", f"Listing already exists: {name}@{version}")

        listing = Listing(
            id=listing_id,
            name=name,
            version=version,
            category=category,
            description=description,
            author=author,
            tags=tags or [],
            compatibility=compatibility or ["any"],
            bundle_path=bundle_path,
            dependencies=dependencies or [],
        )

        self._listings[listing_id] = listing
        self._indexer.index(listing)
        self._save(listing)
        return listing

    def get(self, listing_id: str) -> Listing | None:
        return self._listings.get(listing_id)

    def get_by_name(self, name: str, version: str | None = None) -> Listing | None:
        for listing in self._listings.values():
            if listing.name == name:
                if version is None or listing.version == version:
                    return listing
        return None

    def update(self, listing_id: str, **kwargs: Any) -> Listing:
        listing = self._listings.get(listing_id)
        if not listing:
            raise MarketplaceError("NOT_FOUND", f"Listing not found: {listing_id}")

        for key, value in kwargs.items():
            if hasattr(listing, key):
                setattr(listing, key, value)
        listing.updated_at = time.time()

        self._save(listing)
        return listing

    def delete(self, listing_id: str) -> bool:
        listing = self._listings.pop(listing_id, None)
        if listing:
            self._indexer.unindex(listing_id, listing)
            path = LISTINGS_DIR / f"{listing_id}.json"
            if path.exists():
                path.unlink()
            return True
        return False

    def search(
        self,
        query: str,
        category: str | None = None,
        tags: list[str] | None = None,
        installed: bool | None = None,
        limit: int = 20,
    ) -> list[Listing]:
        ids = self._indexer.search(query, limit=limit * 2)
        results = []
        for lid in ids:
            listing = self._listings.get(lid)
            if not listing:
                continue
            if category and listing.category != category:
                continue
            if tags and not any(t in listing.tags for t in tags):
                continue
            if installed is not None and listing.installed != installed:
                continue
            results.append(listing)
            if len(results) >= limit:
                break
        return results

    def list_all(self, category: str | None = None, sort_by: str = "downloads") -> list[Listing]:
        listings = list(self._listings.values())
        if category:
            listings = [l for l in listings if l.category == category]
        if sort_by == "downloads":
            listings.sort(key=lambda l: l.downloads, reverse=True)
        elif sort_by == "rating":
            listings.sort(key=lambda l: l.rating * l.rating_count, reverse=True)
        elif sort_by == "updated":
            listings.sort(key=lambda l: l.updated_at, reverse=True)
        elif sort_by == "name":
            listings.sort(key=lambda l: l.name)
        return listings

    def get_categories(self) -> list[str]:
        cats = set(l.category for l in self._listings.values())
        return sorted(cats)

    def get_tags(self) -> list[str]:
        tags = set()
        for l in self._listings.values():
            tags.update(l.tags)
        return sorted(tags)

    def update_rating(self, listing_id: str, rating: float) -> Listing:
        listing = self._listings.get(listing_id)
        if not listing:
            raise MarketplaceError("NOT_FOUND", f"Listing not found: {listing_id}")
        # Weighted average: new_avg = (old_avg * count + new_rating) / (count + 1)
        total = listing.rating * listing.rating_count + rating
        listing.rating_count += 1
        listing.rating = total / listing.rating_count
        listing.updated_at = time.time()
        self._save(listing)
        return listing

    def increment_downloads(self, listing_id: str) -> Listing:
        listing = self._listings.get(listing_id)
        if not listing:
            raise MarketplaceError("NOT_FOUND", f"Listing not found: {listing_id}")
        listing.downloads += 1
        self._save(listing)
        return listing

    def add_review(self, listing_id: str, review: Review) -> Listing:
        listing = self._listings.get(listing_id)
        if not listing:
            raise MarketplaceError("NOT_FOUND", f"Listing not found: {listing_id}")
        listing.reviews.append(review)
        self.update_rating(listing_id, review.rating)
        self._save(listing)
        return listing

    def get_catalog(self) -> MarketplaceCatalog:
        return MarketplaceCatalog(
            total=list(self._listings.values()),
            categories=self.get_categories(),
            tags=self.get_tags(),
            featured=self._get_featured(),
        )

    def _get_featured(self) -> list[Listing]:
        """Return top-rated installed plugins."""
        installed = [l for l in self._listings.values() if l.installed]
        installed.sort(key=lambda l: l.rating * l.rating_count, reverse=True)
        return installed[:5]

    def stats(self) -> dict[str, Any]:
        total = len(self._listings)
        installed = sum(1 for l in self._listings.values() if l.installed)
        enabled = sum(1 for l in self._listings.values() if l.enabled)
        return {
            "total_listings": total,
            "installed": installed,
            "enabled": enabled,
            "categories": len(self.get_categories()),
            "total_downloads": sum(l.downloads for l in self._listings.values()),
            "total_reviews": sum(l.rating_count for l in self._listings.values()),
        }


# ── MarketplaceCatalog ────────────────────────────────────────────────────────

@dataclass
class MarketplaceCatalog:
    total: list[Listing]
    categories: list[str]
    tags: list[str]
    featured: list[Listing]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_count": len(self.total),
            "categories": self.categories,
            "tags": self.tags,
            "featured": [l.to_dict() for l in self.featured],
        }

    def filter(
        self,
        category: str | None = None,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> list[Listing]:
        results = self.total
        if category:
            results = [l for l in results if l.category == category]
        if tags:
            results = [l for l in results if any(t in l.tags for t in tags)]
        if search:
            indexer = PluginIndexer()
            # Re-search
            ids = indexer.search(search)
            id_set = set(ids)
            results = [l for l in results if l.id in id_set]
        return results


# ── Module-level helpers ─────────────────────────────────────────────────────

def get_store() -> PluginStore:
    return PluginStore()


def search_plugins(query: str, limit: int = 20) -> list[Listing]:
    return get_store().search(query, limit=limit)


def get_catalog() -> MarketplaceCatalog:
    return get_store().get_catalog()


def create_listing(**kwargs: Any) -> Listing:
    return get_store().create_listing(**kwargs)