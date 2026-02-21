import base64
import os
import random
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
    except ValueError as exc:
        raise SystemExit(f"{name} must be a number, got: {raw}") from exc


def bool_env(name: str, default: str) -> bool:
    return env_or_default(name, default).lower() in ("true", "1", "yes")


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


def strip_spotify_link(name: str) -> str:
    return re.sub(r"\s*\[spotify\]\(https://open\.spotify\.com/artist/[a-zA-Z0-9]+\)", "", name).rstrip()


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


def parse_band_entry(name: str) -> tuple[str, int | None]:
    match = re.match(r"^(.+?)\s*\((\d+)\)\s*$", name)
    if match:
        return match.group(1).rstrip(), int(match.group(2))
    return name, None


def load_bands(
    markdown_path: Path, not_found_hint: str, skipped_hint: str
) -> tuple[list[str], set[str], dict[str, int]]:
    bands: list[str] = []
    intentionally_skipped_from_file: set[str] = set()
    track_overrides: dict[str, int] = {}
    for line in markdown_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if match:
            raw_name = match.group(1)
            base_name = strip_status_hints(raw_name, not_found_hint, skipped_hint)
            base_name = strip_spotify_link(base_name)
            base_name, override = parse_band_entry(base_name)
            bands.append(base_name)
            if override is not None:
                track_overrides[base_name] = override
            if skipped_hint and raw_name.endswith(skipped_hint):
                intentionally_skipped_from_file.add(base_name)
    return bands, intentionally_skipped_from_file, track_overrides


def update_bands_hints(
    markdown_path: Path,
    not_found_exact: set[str],
    intentionally_skipped: set[str],
    not_found_hint: str,
    skipped_hint: str,
    artist_urls: dict[str, str] | None = None,
):
    updated_lines: list[str] = []
    not_found_hint_text = format_hint(not_found_hint)
    skipped_hint_text = format_hint(skipped_hint)
    urls = artist_urls or {}

    for line in markdown_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(\s*-\s+)(.+?)\s*$", line)
        if not match:
            updated_lines.append(line)
            continue

        prefix, raw_name = match.groups()
        base_name = strip_status_hints(raw_name, not_found_hint, skipped_hint)
        base_name = strip_spotify_link(base_name)
        if base_name in intentionally_skipped:
            updated_lines.append(f"{prefix}{base_name}{skipped_hint_text}")
        elif base_name in not_found_exact:
            updated_lines.append(f"{prefix}{base_name}{not_found_hint_text}")
        else:
            link = f" [spotify]({urls[base_name]})" if base_name in urls else ""
            updated_lines.append(f"{prefix}{base_name}{link}")

    markdown_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def append_playlist_url(markdown_path: Path, playlist_url: str):
    playlist_link_pattern = re.compile(r"^\[.*\]\(https://open\.spotify\.com/playlist/\w+\)$")
    lines = markdown_path.read_text(encoding="utf-8").splitlines()

    # Replace existing playlist link if present
    replaced = False
    for i, line in enumerate(lines):
        if playlist_link_pattern.match(line.strip()):
            lines[i] = f"[Spotify Playlist]({playlist_url})"
            replaced = True
            break

    if not replaced:
        lines.append("")
        lines.append(f"[Spotify Playlist]({playlist_url})")

    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def create_playlist(sp: spotipy.Spotify, user_id: str, name: str, description: str = "") -> str:
    playlist = sp.user_playlist_create(user=user_id, name=name, public=True, description=description)
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


def find_existing_playlist(sp: spotipy.Spotify, user_id: str, name: str) -> dict | None:
    normalized_target = normalize_playlist_name(name)
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=50, offset=offset)
        items = page.get("items", [])
        if not items:
            return None
        for playlist in items:
            if (
                playlist.get("owner", {}).get("id") == user_id
                and normalize_playlist_name(playlist.get("name", "")) == normalized_target
            ):
                return playlist
        if len(items) < 50:
            return None
        offset += 50


def get_playlist_track_uris(sp: spotipy.Spotify, playlist_id: str) -> list[str]:
    uris: list[str] = []
    results = sp.playlist_tracks(playlist_id, fields="items.track.uri,next")
    while results:
        for item in results.get("items", []):
            track = item.get("track")
            if track and track.get("uri"):
                uris.append(track["uri"])
        if results.get("next"):
            results = sp.next(results)
        else:
            break
    return uris


def replace_playlist_tracks(sp: spotipy.Spotify, playlist_id: str, uris: list[str], chunk_size: int):
    sp.playlist_replace_items(playlist_id, uris[:100])
    for i in range(100, len(uris), chunk_size):
        sp.playlist_add_items(playlist_id, uris[i : i + chunk_size])


def add_tracks_in_chunks(sp: spotipy.Spotify, playlist_id: str, uris: list[str], chunk_size: int):
    for i in range(0, len(uris), chunk_size):
        sp.playlist_add_items(playlist_id, uris[i : i + chunk_size])


def upload_cover_image(sp: spotipy.Spotify, playlist_id: str, cover_image: Path):
    image_bytes = cover_image.read_bytes()
    if len(image_bytes) > 256 * 1024:
        print(f"Warning: Cover image is {len(image_bytes) // 1024} KB (Spotify limit is 256 KB), skipping upload.")
        return
    try:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        sp.playlist_upload_cover_image(playlist_id, image_b64)
        print(f"Uploaded cover image: {cover_image.name}")
    except spotipy.SpotifyException as e:
        print(f"Warning: Failed to upload cover image: {e}")


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
    cover_image_env = env_or_default("PLAYLIST_COVER_IMAGE", "")
    cover_image = resolve_path(cover_image_env) if cover_image_env else None
    scopes_raw = env_or_default("SPOTIFY_SCOPES", "playlist-modify-private playlist-modify-public")
    if cover_image:
        scopes_raw += " ugc-image-upload"
    scopes = parse_scopes(scopes_raw)
    token_cache_path = resolve_path(env_or_default("SPOTIFY_TOKEN_CACHE_PATH", ".spotify_cache"))
    shuffle_tracks = bool_env("SHUFFLE_TRACKS", "false")
    dry_run = bool_env("DRY_RUN", "false")
    force_recreate = bool_env("FORCE_RECREATE", "false")
    playlist_description = env_or_default("PLAYLIST_DESCRIPTION", "")

    if not bands_file.exists():
        raise SystemExit(f"Bands file not found: {bands_file}")

    if track_limit <= 0:
        raise SystemExit("TOP_TRACKS_PER_ARTIST must be > 0")
    if search_limit <= 0:
        raise SystemExit("SPOTIFY_SEARCH_LIMIT must be > 0")
    if chunk_size <= 0:
        raise SystemExit("SPOTIFY_ADD_CHUNK_SIZE must be > 0")
    if cover_image and not cover_image.exists():
        raise SystemExit(f"Cover image not found: {cover_image}")

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

    bands, intentionally_skipped_bands, track_overrides = load_bands(bands_file, not_found_hint, skipped_hint)

    all_track_uris: list[str] = []
    unresolved: list[str] = []
    not_found_exact: set[str] = set()
    intentionally_skipped: set[str] = set()
    artist_urls: dict[str, str] = {}

    for i, band in enumerate(bands, start=1):
        query = normalize_artist_query(band, intentionally_skipped_bands)
        if not query:
            print(f"  [{i}/{len(bands)}] {band} — skipped")
            intentionally_skipped.add(band)
            unresolved.append(band)
            continue

        artist = pick_best_artist(sp, query, market, search_limit)
        if not artist:
            print(f"  [{i}/{len(bands)}] {band} — not found")
            not_found_exact.add(band)
            unresolved.append(band)
            continue

        url = artist.get("external_urls", {}).get("spotify", "")
        if url:
            artist_urls[band] = url

        band_track_limit = track_overrides.get(band, track_limit)
        artist_tracks = top_tracks_for_artist(sp, artist["id"], market=market, track_limit=band_track_limit)
        if not artist_tracks:
            print(f"  [{i}/{len(bands)}] {band} — no tracks")
            unresolved.append(band)
            continue

        print(f"  [{i}/{len(bands)}] {band} ✓ {len(artist_tracks)} tracks")
        all_track_uris.extend(artist_tracks)

    deduped_track_uris = list(dict.fromkeys(all_track_uris))

    if shuffle_tracks:
        random.shuffle(deduped_track_uris)

    if dry_run:
        matched_count = len(bands) - len(unresolved)
        print("--- DRY RUN (no changes will be made) ---\n")
        print(f"Playlist name: {playlist_name}")
        print(f"Total tracks:  {len(deduped_track_uris)} (deduplicated)")
        if shuffle_tracks:
            print("Shuffle:       on")
        if cover_image:
            print(f"Cover image:   {cover_image}")
        print(f"\nMatched {matched_count} / {len(bands)} artists")
        if unresolved:
            print("\nNot resolved:")
            for name in unresolved:
                if name in intentionally_skipped:
                    print(f"  - {name} (intentionally skipped)")
                else:
                    print(f"  - {name} (no exact match)")
        return

    update_bands_hints(bands_file, not_found_exact, intentionally_skipped, not_found_hint, skipped_hint, artist_urls)

    if not deduped_track_uris:
        raise SystemExit("No tracks found. Playlist was not created.")

    existing = find_existing_playlist(sp, user_id, playlist_name)

    if existing and not force_recreate:
        existing_uris = get_playlist_track_uris(sp, existing["id"])
        playlist_id = existing["id"]
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"

        if set(existing_uris) == set(deduped_track_uris):
            if cover_image:
                upload_cover_image(sp, playlist_id, cover_image)
            append_playlist_url(bands_file, playlist_url)
            matched_count = len(bands) - len(unresolved)
            print(f"\nPlaylist unchanged: {playlist_name}")
            print(f"URL: {playlist_url}")
            print(f"\nSummary: {matched_count}/{len(bands)} artists matched, {len(deduped_track_uris)} tracks")
            if unresolved:
                print("\nArtists not resolved automatically:")
                for name in unresolved:
                    print(f"- {name}")
            return

        # Tracks changed — update in-place
        replace_playlist_tracks(sp, playlist_id, deduped_track_uris, chunk_size)
        if cover_image:
            upload_cover_image(sp, playlist_id, cover_image)
        append_playlist_url(bands_file, playlist_url)
        matched_count = len(bands) - len(unresolved)
        print(f"\nUpdated playlist: {playlist_name}")
        print(f"URL: {playlist_url}")
        print(f"\nSummary: {matched_count}/{len(bands)} artists matched, {len(deduped_track_uris)} tracks")
        if unresolved:
            print("\nArtists not resolved automatically:")
            for name in unresolved:
                print(f"- {name}")
        return

    if existing and force_recreate:
        deleted_count = delete_existing_playlists(sp, user_id, playlist_name)
        if deleted_count:
            print(f"Force recreate: removed {deleted_count} existing playlist(s)")

    print("Creating playlist as: public")

    playlist_id = create_playlist(sp, user_id, playlist_name, playlist_description)
    add_tracks_in_chunks(sp, playlist_id, deduped_track_uris, chunk_size)

    if cover_image:
        upload_cover_image(sp, playlist_id, cover_image)

    playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    append_playlist_url(bands_file, playlist_url)
    matched_count = len(bands) - len(unresolved)
    print(f"\nCreated playlist: {playlist_name}")
    print(f"URL: {playlist_url}")
    print(f"\nSummary: {matched_count}/{len(bands)} artists matched, {len(deduped_track_uris)} tracks")

    if unresolved:
        print("\nArtists not resolved automatically:")
        for name in unresolved:
            print(f"- {name}")


if __name__ == "__main__":
    main()
