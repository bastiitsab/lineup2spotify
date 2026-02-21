import os
import re
from pathlib import Path

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyPKCE


SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def env_or_default(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value if value else default


def int_env(name: str, default: str) -> int:
    raw = env_or_default(name, default)
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"{name} must be a number, got: {raw}")


def parse_scopes(value: str) -> str:
    parts = [part.strip() for part in re.split(r"[\s,]+", value) if part.strip()]
    if not parts:
        raise SystemExit("SPOTIFY_SCOPES must not be empty.")
    return " ".join(parts)


def normalize_playlist_name(name: str) -> str:
    normalized = name.lower()
    normalized = normalized.replace("–", "-").replace("—", "-").replace("−", "-")
    normalized = normalized.replace("’", "'")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*-\s*", " - ", normalized)
    return normalized.strip()


def resolve_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return SCRIPT_DIR / path


def strip_status_hints(name: str, not_found_hint: str, skipped_hint: str) -> str:
    for hint in (not_found_hint, skipped_hint):
        if hint and name.endswith(f" {hint}"):
            return name[: -len(hint) - 1].rstrip()
        if hint and name.endswith(hint):
            return name[: -len(hint)].rstrip()
    return name


def format_hint(hint: str) -> str:
    return f" {hint.lstrip()}" if hint else ""


def derive_playlist_name(markdown_path: Path) -> str:
    title = ""
    for line in markdown_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if match:
            title = match.group(1).strip()
            break

    if not title:
        return f"{markdown_path.stem} - Top 5 je Band"

    return f"{title} - Top 5 je Band"


def load_bands(markdown_path: Path, not_found_hint: str, skipped_hint: str) -> tuple[list[str], set[str]]:
    bands: list[str] = []
    intentionally_skipped_from_file: set[str] = set()
    for line in markdown_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if match:
            raw_name = match.group(1)
            base_name = strip_status_hints(raw_name, not_found_hint, skipped_hint)
            bands.append(base_name)
            if skipped_hint and raw_name.endswith(skipped_hint):
                intentionally_skipped_from_file.add(base_name)
    return bands, intentionally_skipped_from_file


def update_bands_hints(
    markdown_path: Path,
    not_found_exact: set[str],
    intentionally_skipped: set[str],
    not_found_hint: str,
    skipped_hint: str,
):
    updated_lines: list[str] = []
    not_found_hint_text = format_hint(not_found_hint)
    skipped_hint_text = format_hint(skipped_hint)

    for line in markdown_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(\s*-\s+)(.+?)\s*$", line)
        if not match:
            updated_lines.append(line)
            continue

        prefix, raw_name = match.groups()
        base_name = strip_status_hints(raw_name, not_found_hint, skipped_hint)
        if base_name in intentionally_skipped:
            updated_lines.append(f"{prefix}{base_name}{skipped_hint_text}")
        elif base_name in not_found_exact:
            updated_lines.append(f"{prefix}{base_name}{not_found_hint_text}")
        else:
            updated_lines.append(f"{prefix}{base_name}")

    markdown_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def normalize_artist_query(name: str, intentionally_skipped_bands: set[str]) -> str:
    if name in intentionally_skipped_bands:
        return ""
    return name


def pick_best_artist(sp: spotipy.Spotify, query: str, market: str, search_limit: int):
    if not query:
        return None
    result = sp.search(q=f"artist:{query}", type="artist", limit=search_limit, market=market)
    items = result.get("artists", {}).get("items", [])
    if not items:
        return None

    lowered_query = query.lower()
    for artist in items:
        if artist.get("name", "").lower() == lowered_query:
            return artist
    return None


def top_tracks_for_artist(sp: spotipy.Spotify, artist_id: str, market: str, track_limit: int) -> list[str]:
    tracks = sp.artist_top_tracks(artist_id, country=market).get("tracks", [])
    uris: list[str] = []
    for track in tracks:
        uri = track.get("uri")
        if uri and uri not in uris:
            uris.append(uri)
        if len(uris) >= track_limit:
            break
    return uris


def create_playlist(sp: spotipy.Spotify, user_id: str, name: str) -> str:
    playlist = sp.user_playlist_create(user=user_id, name=name, public=True)
    return playlist["id"]


def delete_existing_playlists(sp: spotipy.Spotify, user_id: str, name: str) -> int:
    deleted = 0
    seen_playlist_ids: set[str] = set()
    normalized_target_name = normalize_playlist_name(name)

    while True:
        found_in_pass = False
        offset = 0

        while True:
            page = sp.current_user_playlists(limit=50, offset=offset)
            items = page.get("items", [])
            if not items:
                break

            for playlist in items:
                playlist_id = playlist.get("id")
                playlist_name = playlist.get("name")
                owner_id = playlist.get("owner", {}).get("id")
                normalized = normalize_playlist_name(playlist_name or "")

                if (
                    playlist_id
                    and normalized == normalized_target_name
                    and owner_id == user_id
                    and playlist_id not in seen_playlist_ids
                ):
                    sp.current_user_unfollow_playlist(playlist_id)
                    seen_playlist_ids.add(playlist_id)
                    deleted += 1
                    found_in_pass = True

            if len(items) < 50:
                break
            offset += 50

        if not found_in_pass:
            break

    return deleted


def add_tracks_in_chunks(sp: spotipy.Spotify, playlist_id: str, uris: list[str], chunk_size: int):
    for i in range(0, len(uris), chunk_size):
        sp.playlist_add_items(playlist_id, uris[i : i + chunk_size])


def main():
    load_dotenv(dotenv_path=ENV_FILE, override=True)

    client_id = require_env("SPOTIFY_CLIENT_ID")
    redirect_uri = env_or_default("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:4202")
    bands_file = resolve_path(require_env("BANDS_FILE_PATH"))
    market = env_or_default("SPOTIFY_MARKET", "DE")
    not_found_hint = env_or_default("NOT_FOUND_HINT_TEXT", "_(not added: no exact Spotify artist match)_").lstrip()
    skipped_hint = env_or_default("SKIPPED_HINT_TEXT", "_(not added: intentionally skipped)_").lstrip()
    track_limit = int_env("TOP_TRACKS_PER_ARTIST", "5")
    search_limit = int_env("SPOTIFY_SEARCH_LIMIT", "5")
    chunk_size = int_env("SPOTIFY_ADD_CHUNK_SIZE", "100")
    scopes = parse_scopes(env_or_default("SPOTIFY_SCOPES", "playlist-modify-private playlist-modify-public"))
    token_cache_path = resolve_path(env_or_default("SPOTIFY_TOKEN_CACHE_PATH", ".spotify_cache"))

    if not bands_file.exists():
        raise SystemExit(f"Bands file not found: {bands_file}")

    if track_limit <= 0:
        raise SystemExit("TOP_TRACKS_PER_ARTIST must be > 0")
    if search_limit <= 0:
        raise SystemExit("SPOTIFY_SEARCH_LIMIT must be > 0")
    if chunk_size <= 0:
        raise SystemExit("SPOTIFY_ADD_CHUNK_SIZE must be > 0")

    playlist_name = derive_playlist_name(bands_file)

    auth = SpotifyPKCE(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scopes,
        open_browser=True,
        cache_path=str(token_cache_path),
    )

    sp = spotipy.Spotify(auth_manager=auth)
    user_id = sp.current_user()["id"]

    bands, intentionally_skipped_bands = load_bands(bands_file, not_found_hint, skipped_hint)

    all_track_uris: list[str] = []
    unresolved: list[str] = []
    not_found_exact: set[str] = set()
    intentionally_skipped: set[str] = set()

    for band in bands:
        query = normalize_artist_query(band, intentionally_skipped_bands)
        if not query:
            intentionally_skipped.add(band)
            unresolved.append(band)
            continue

        artist = pick_best_artist(sp, query, market, search_limit)
        if not artist:
            not_found_exact.add(band)
            unresolved.append(band)
            continue

        artist_tracks = top_tracks_for_artist(sp, artist["id"], market=market, track_limit=track_limit)
        if not artist_tracks:
            unresolved.append(band)
            continue

        all_track_uris.extend(artist_tracks)

    update_bands_hints(bands_file, not_found_exact, intentionally_skipped, not_found_hint, skipped_hint)

    deduped_track_uris = list(dict.fromkeys(all_track_uris))

    if not deduped_track_uris:
        raise SystemExit("No tracks found. Playlist was not created.")

    deleted_count = delete_existing_playlists(sp, user_id, playlist_name)
    if deleted_count:
        print(f"Removed {deleted_count} existing playlist(s) named: {playlist_name}")

    print("Creating playlist as: public")

    playlist_id = create_playlist(sp, user_id, playlist_name)
    add_tracks_in_chunks(sp, playlist_id, deduped_track_uris, chunk_size)

    playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    print(f"Created playlist: {playlist_name}")
    print(f"URL: {playlist_url}")

    if unresolved:
        print("\nArtists not resolved automatically:")
        for name in unresolved:
            print(f"- {name}")


if __name__ == "__main__":
    main()
