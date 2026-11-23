#!/usr/bin/env python3
"""Generate a personal AltStore / SideStore source from GitHub releases.

Inputs
------
source.json     source-level metadata: name, identifier, tintColor, ...
apps/*.json     one file per app; each names the upstream GitHub repo to watch,
                which release asset is the iOS build, and how to present it.

Outputs
-------
generated/apps.json     the source document (primary URL)
alt_store.json          identical copy under the classic filename

Every config field lives in JSON so adding an app needs no code change: drop a
file into apps/, commit, and the scheduled workflow picks it up.

Standard library only -- GitHub Actions needs no dependency install step.
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
USER_AGENT = "pyramid-altstore-self"
TIMEOUT = 60
DEFAULT_MIN_OS = "15.0"
DEFAULT_TINT = "#8E8E93"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def log(message):
    print(message, flush=True)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def http_get_json(url, token=None):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_releases(repo, token, pages=2):
    """Return releases newest-first, at most `pages` x 100 of them."""
    releases = []
    for page in range(1, pages + 1):
        batch = http_get_json(
            f"{API}/repos/{repo}/releases?per_page=100&page={page}", token
        )
        if not batch:
            break
        releases.extend(batch)
        if len(batch) < 100:
            break
    return releases


def find_asset(release, name):
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            return asset
    return None


def pick_asset(release, pattern):
    """First release asset whose name matches the app's asset regex."""
    rx = re.compile(pattern, re.IGNORECASE)
    for asset in release.get("assets", []):
        if rx.search(asset.get("name", "")):
            return asset
    return None


def release_notes(app, release, asset):
    """Changelog text: a small JSON asset when the app publishes one, else the body."""
    spec = app.get("notesFromAsset")
    if spec:
        extra = find_asset(release, spec.get("name", ""))
        if extra is not None:
            try:
                # Release assets redirect to a CDN; urllib follows that for us.
                data = http_get_json(extra["browser_download_url"])
            except Exception as exc:  # network hiccup must not lose the release
                log(f"    notes asset unavailable ({type(exc).__name__}); using release body")
            else:
                locale = spec.get("locale")
                localized = data.get("notesByLocale") or {}
                if locale and isinstance(localized.get(locale), str):
                    text = localized[locale].strip()
                    if text:
                        return text
                text = (data.get("notes") or "").strip()
                if text:
                    return text
    return (release.get("body") or "").strip()


# --------------------------------------------------------------------------- #
# Building the source
# --------------------------------------------------------------------------- #

def version_entry(app, release, asset):
    tag = release.get("tag_name", "")
    prefix = app.get("versionStripPrefix") or ""
    version = tag[len(prefix):] if prefix and tag.startswith(prefix) else tag

    entry = {
        "version": version,
        "date": release.get("published_at", ""),
        "localizedDescription": release_notes(app, release, asset)
        or f"{app['name']} {version}",
        "downloadURL": asset["browser_download_url"],
        "size": asset.get("size", 0),
        "minOSVersion": app.get("minOSVersion", DEFAULT_MIN_OS),
        "_tag": tag,
    }

    # buildVersion must match CFBundleVersion inside the ipa; only set it when the
    # asset name actually carries it (PiliPlus does, DSH Go leaves it at 1).
    pattern = app.get("buildVersionRegex")
    if pattern:
        match = re.search(pattern, asset.get("name", ""), re.IGNORECASE)
        if match:
            entry["buildVersion"] = match.group(1)
    return entry


def collect_versions(app, releases):
    """Map upstream releases to AltStore version entries, newest first."""
    seen = set()
    versions = []
    for release in releases:
        if release.get("draft"):
            continue
        if release.get("prerelease") and not app.get("includePrerelease"):
            continue
        asset = pick_asset(release, app["assetPattern"])
        if asset is None:
            continue
        entry = version_entry(app, release, asset)
        key = (entry["version"], entry["downloadURL"])
        if key in seen:
            continue
        seen.add(key)
        versions.append(entry)

    versions.sort(key=lambda v: v["date"], reverse=True)
    cap = app.get("maxVersions")
    if cap:
        versions = versions[: int(cap)]
    return versions


def app_entry(app, versions):
    latest = versions[0]
    entry = {
        "beta": bool(app.get("beta", False)),
        "name": app["name"],
        "bundleIdentifier": app["bundleIdentifier"],
        "developerName": app["developerName"],
        "subtitle": app["subtitle"],
        "localizedDescription": app["localizedDescription"],
        "version": latest["version"],
        "versionDate": latest["date"],
        "versionDescription": latest["localizedDescription"],
        "downloadURL": latest["downloadURL"],
        "size": latest["size"],
        "iconURL": app["iconURL"],
        "tintColor": app.get("tintColor", DEFAULT_TINT),
        "category": app.get("category", "utilities"),
    }
    shots = app.get("screenshots")
    if shots:
        entry["screenshots"] = {
            "iphone": shots.get("iphone", []),
            "ipad": shots.get("ipad", []),
        }
    entry["appPermissions"] = {
        "entitlements": app.get("entitlements", []),
        "privacy": app.get("privacy", {}),
    }
    entry["versions"] = versions
    return entry


def news_entry(app, versions):
    latest = versions[0]
    version = latest["version"]
    return {
        "appID": app["bundleIdentifier"],
        "caption": f"{app['name']} {version} 已发布",
        "date": latest["date"],
        "identifier": f"{app['id']}-{version}",
        "notify": True,
        "tintColor": app.get("tintColor", DEFAULT_TINT),
        "title": f"{app['name']} {version}",
        "url": f"https://github.com/{app['repo']}/releases/tag/{latest['_tag']}",
    }


def strip_internal(versions):
    for entry in versions:
        entry.pop("_tag", None)


def write_outputs(source):
    payload = json.dumps(source, ensure_ascii=False, indent=2) + "\n"
    generated = ROOT / "generated"
    generated.mkdir(exist_ok=True)
    (generated / "apps.json").write_text(payload, encoding="utf-8")
    (ROOT / "alt_store.json").write_text(payload, encoding="utf-8")


def load_apps():
    configs = []
    for path in sorted((ROOT / "apps").glob("*.json")):
        app = load_json(path)
        app["id"] = app.get("id") or path.stem
        configs.append(app)
    enabled = [a for a in configs if a.get("enabled", True)]
    enabled.sort(key=lambda a: (a.get("order", 1000), a["id"]))
    return enabled


def main():
    token = os.environ.get("GITHUB_TOKEN")
    source_cfg = load_json(ROOT / "source.json")
    apps = load_apps()
    if not apps:
        log("ERROR: no enabled app configs in apps/")
        return 1

    built = []
    missing = []
    for app in apps:
        log(f"[{app['id']}] {app['repo']}")
        try:
            releases = fetch_releases(
                app["repo"], token, pages=int(app.get("maxPages", 2))
            )
        except Exception as exc:
            log(f"  ERROR: cannot fetch releases ({type(exc).__name__}: {exc})")
            missing.append(app["id"])
            continue

        versions = collect_versions(app, releases)
        if not versions:
            log(f"  ERROR: no iOS build found in {len(releases)} releases")
            missing.append(app["id"])
            continue
        log(f"  {len(releases)} releases -> {len(versions)} iOS builds, latest {versions[0]['version']}")
        built.append((app, versions))

    # Never publish a source with an app silently dropped: a transient API error
    # or a moved asset should fail the run, not delete a section of the source.
    if missing:
        log(f"ERROR: no usable release for: {', '.join(missing)}; keeping previous files")
        return 1

    app_entries = []
    news = []
    summary = []
    for app, versions in built:
        news.append(news_entry(app, versions))
        strip_internal(versions)
        app_entries.append(app_entry(app, versions))
        summary.append(f"{app['name']} {versions[0]['version']}")

    featured = [
        entry["bundleIdentifier"]
        for (app, _), entry in zip(built, app_entries)
        if app.get("featured", True)
    ]

    source = {
        "name": source_cfg["name"],
        "identifier": source_cfg["identifier"],
        "website": source_cfg["website"],
        "subtitle": source_cfg["subtitle"],
        "description": source_cfg["description"],
        "iconURL": source_cfg["iconURL"],
        "tintColor": source_cfg.get("tintColor", DEFAULT_TINT),
        "featuredApps": featured,
        "apps": app_entries,
        "news": [n for n in news if _news_enabled(built, n["appID"])],
    }

    write_outputs(source)

    total = sum(len(a["versions"]) for a in app_entries)
    log(f"generated source with {len(app_entries)} apps / {total} versions")
    for line in summary:
        log(f"  {line}")

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as handle:
            handle.write("summary=" + "; ".join(summary) + "\n")
    return 0


def _news_enabled(built, bundle_id):
    for app, _ in built:
        if app["bundleIdentifier"] == bundle_id:
            return bool(app.get("news", True))
    return False


if __name__ == "__main__":
    sys.exit(main())
