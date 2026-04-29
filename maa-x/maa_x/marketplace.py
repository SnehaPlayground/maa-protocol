"""Internal plugin marketplace."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MARKETPLACE_DIR = Path("/tmp/maa-x-marketplace")
LISTINGS_DIR = MARKETPLACE_DIR / "listings"
LISTINGS_DIR.mkdir(parents=True, exist_ok=True)


class MarketplaceError(Exception):
    def __init__(self, code: str, message: str, detail: str | None = None):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(f"[{code}] {message}" + (f": {detail}" if detail else ""))


@dataclass
class Review:
    id: str
    author: str
    rating: int
    title: str
    body: str
    created_at: float = field(default_factory=time.time)
    helpful: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Review":
        return cls(**d)


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
    compatibility: list[str] = field(default_factory=list)
    bundle_path: str | None = None
    bundle_size_bytes: int = 0
    downloads: int = 0
    rating: float = 0.0
    rating_count: int = 0
    reviews: list[Review] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    installed: bool = False
    enabled: bool = False
    status: str = "active"

    def is_compatible(self, maa_version: str) -> bool:
        return not self.compatibility or maa_version in self.compatibility or "any" in self.compatibility

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["reviews"] = [r.to_dict() for r in self.reviews]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Listing":
        d = dict(d)
        d["reviews"] = [Review.from_dict(r) for r in d.get("reviews", [])]
        return cls(**d)


class PluginIndexer:
    def __init__(self) -> None:
        self._term_to_ids: dict[str, set[str]] = {}
        self._listing_ids: set[str] = set()

    def index(self, listing: Listing) -> None:
        self._listing_ids.add(listing.id)
        terms = set((f"{listing.name} {listing.description} {' '.join(listing.tags)} {listing.category}").lower().split())
        for term in terms:
            self._term_to_ids.setdefault(term, set()).add(listing.id)

    def unindex(self, listing_id: str, listing: Listing) -> None:
        self._listing_ids.discard(listing_id)
        terms = set((f"{listing.name} {listing.description} {' '.join(listing.tags)} {listing.category}").lower().split())
        for term in terms:
            self._term_to_ids.get(term, set()).discard(listing_id)

    def search(self, query: str, limit: int = 20) -> list[str]:
        query_terms = [t for t in query.lower().split() if len(t) >= 2]
        if not query_terms:
            return list(self._listing_ids)[:limit]
        scores: dict[str, int] = {}
        for term in query_terms:
            for lid in self._term_to_ids.get(term, set()):
                scores[lid] = scores.get(lid, 0) + 1
        return sorted(scores, key=lambda x: scores[x], reverse=True)[:limit]


@dataclass
class MarketplaceCatalog:
    total: list[Listing]
    categories: list[str]
    tags: list[str]
    featured: list[Listing]

    def to_dict(self) -> dict[str, Any]:
        return {"total_count": len(self.total), "categories": self.categories, "tags": self.tags, "featured": [l.to_dict() for l in self.featured]}


class PluginStore:
    def __init__(self) -> None:
        self._listings: dict[str, Listing] = {}
        self._indexer = PluginIndexer()
        self._load()

    def _load(self) -> None:
        for f in LISTINGS_DIR.glob("*.json"):
            try:
                listing = Listing.from_dict(json.loads(f.read_text()))
                self._listings[listing.id] = listing
                self._indexer.index(listing)
            except Exception:
                pass

    def _save(self, listing: Listing) -> None:
        LISTINGS_DIR.mkdir(parents=True, exist_ok=True)
        (LISTINGS_DIR / f"{listing.id}.json").write_text(json.dumps(listing.to_dict(), indent=2))

    def _make_id(self, name: str) -> str:
        return hashlib.sha256(name.encode()).hexdigest()[:16]

    def create_listing(self, name: str, version: str, category: str, description: str = "", author: str = "unknown", tags: list[str] | None = None, compatibility: list[str] | None = None, bundle_path: str | None = None, dependencies: list[str] | None = None) -> Listing:
        listing_id = self._make_id(f"{name}:{version}")
        if listing_id in self._listings:
            raise MarketplaceError("DUPLICATE_LISTING", f"Listing already exists: {name}@{version}")
        listing = Listing(listing_id, name, version, category, description, author, tags=tags or [], compatibility=compatibility or ["any"], bundle_path=bundle_path, dependencies=dependencies or [])
        self._listings[listing_id] = listing
        self._indexer.index(listing)
        self._save(listing)
        return listing

    def get(self, listing_id: str) -> Listing | None:
        return self._listings.get(listing_id)

    def get_by_name(self, name: str, version: str | None = None) -> Listing | None:
        for listing in self._listings.values():
            if listing.name == name and (version is None or listing.version == version):
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
        if not listing:
            return False
        self._indexer.unindex(listing_id, listing)
        path = LISTINGS_DIR / f"{listing_id}.json"
        if path.exists():
            path.unlink()
        return True

    def search(self, query: str, category: str | None = None, tags: list[str] | None = None, installed: bool | None = None, limit: int = 20) -> list[Listing]:
        ids = self._indexer.search(query, limit=limit * 2)
        out = []
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
            out.append(listing)
            if len(out) >= limit:
                break
        return out

    def list_all(self, category: str | None = None, sort_by: str = "downloads") -> list[Listing]:
        listings = list(self._listings.values())
        if category:
            listings = [l for l in listings if l.category == category]
        key_map = {
            "downloads": lambda l: l.downloads,
            "rating": lambda l: l.rating * l.rating_count,
            "updated": lambda l: l.updated_at,
            "name": lambda l: l.name,
        }
        reverse = sort_by != "name"
        listings.sort(key=key_map.get(sort_by, key_map["downloads"]), reverse=reverse)
        return listings

    def get_categories(self) -> list[str]:
        return sorted({l.category for l in self._listings.values()})

    def get_tags(self) -> list[str]:
        tags = set()
        for l in self._listings.values():
            tags.update(l.tags)
        return sorted(tags)

    def update_rating(self, listing_id: str, rating: float) -> Listing:
        listing = self._listings.get(listing_id)
        if not listing:
            raise MarketplaceError("NOT_FOUND", f"Listing not found: {listing_id}")
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
        installed = [l for l in self._listings.values() if l.installed]
        installed.sort(key=lambda l: l.rating * l.rating_count, reverse=True)
        return MarketplaceCatalog(list(self._listings.values()), self.get_categories(), self.get_tags(), installed[:5])

    def stats(self) -> dict[str, Any]:
        return {"total_listings": len(self._listings), "installed": sum(1 for l in self._listings.values() if l.installed), "enabled": sum(1 for l in self._listings.values() if l.enabled), "categories": len(self.get_categories()), "total_downloads": sum(l.downloads for l in self._listings.values()), "total_reviews": sum(l.rating_count for l in self._listings.values())}


def get_store() -> PluginStore:
    return PluginStore()


def search_plugins(query: str, limit: int = 20) -> list[Listing]:
    return get_store().search(query, limit=limit)


def get_catalog() -> MarketplaceCatalog:
    return get_store().get_catalog()


def create_listing(**kwargs: Any) -> Listing:
    return get_store().create_listing(**kwargs)
