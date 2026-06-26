import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

README_PATH = "README.md"
START_MARKER = "<!-- SPOTIFY-NOW-PLAYING:START -->"
END_MARKER = "<!-- SPOTIFY-NOW-PLAYING:END -->"


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"Missing required env var: {name}")
        sys.exit(1)
    return value


def http_post(url: str, data: dict, headers: dict) -> dict:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    payload = http_post("https://accounts.spotify.com/api/token", data, headers)
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Failed to get Spotify access token")
    return token


def extract_track(track_obj: dict) -> tuple[str, str, str] | None:
    if not track_obj:
        return None
    name = (track_obj.get("name") or "Unknown Track").strip()
    artists = track_obj.get("artists") or []
    artist_names = ", ".join(a.get("name", "") for a in artists if a.get("name")) or "Unknown Artist"
    external = track_obj.get("external_urls") or {}
    url = external.get("spotify", "https://open.spotify.com/")
    return name, artist_names, url


def get_now_playing(access_token: str) -> tuple[str, str, str, bool]:
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        req = urllib.request.Request(
            "https://api.spotify.com/v1/me/player/currently-playing",
            headers=headers,
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            if status == 204:
                raise urllib.error.HTTPError(req.full_url, 204, "No Content", hdrs=None, fp=None)
            data = json.loads(resp.read().decode("utf-8"))
            item = extract_track(data.get("item"))
            if item:
                return item[0], item[1], item[2], True
    except urllib.error.HTTPError as err:
        if err.code not in (204, 401, 403, 429):
            raise

    recent = http_get("https://api.spotify.com/v1/me/player/recently-played?limit=1", headers)
    items = recent.get("items") or []
    if not items:
        return "Nothing playing", "Spotify", "https://open.spotify.com/", False

    track = extract_track((items[0] or {}).get("track"))
    if not track:
        return "Nothing playing", "Spotify", "https://open.spotify.com/", False

    return track[0], track[1], track[2], False


def build_block(title: str, artists: str, url: str, is_playing: bool) -> str:
    state = "Now Playing" if is_playing else "Last Played"
    return "\n".join(
        [
            START_MARKER,
            '<p align="center">',
            f"  🎵 <b>{state}</b><br/>",
            f"  <b>{title}</b> • {artists}<br/>",
            f'  <a href="{url}" target="_blank">',
            '    <img src="https://img.shields.io/badge/Listen%20on-Spotify-1DB954?style=for-the-badge&logo=spotify&logoColor=white" alt="Listen on Spotify" />',
            "  </a>",
            "</p>",
            END_MARKER,
        ]
    )


def update_readme(new_block: str) -> bool:
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
        flags=re.DOTALL,
    )

    if not pattern.search(content):
        raise RuntimeError("Spotify markers not found in README.md")

    updated = pattern.sub(new_block, content, count=1)
    if updated == content:
        return False

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(updated)
    return True


def main() -> None:
    client_id = require_env("SPOTIFY_CLIENT_ID")
    client_secret = require_env("SPOTIFY_CLIENT_SECRET")
    refresh_token = require_env("SPOTIFY_REFRESH_TOKEN")

    access_token = get_access_token(client_id, client_secret, refresh_token)
    title, artists, url, is_playing = get_now_playing(access_token)
    block = build_block(title, artists, url, is_playing)

    changed = update_readme(block)
    print("README updated" if changed else "No README changes")


if __name__ == "__main__":
    main()
