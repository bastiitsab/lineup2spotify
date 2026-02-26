# Spotify API Changes — February 2026

Spotify announced breaking changes to the Web API effective **March 9, 2026** for existing integrations.

- [Blog post](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security)
- [Changelog](https://developer.spotify.com/documentation/web-api/references/changes/february-2026)
- [Migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)

## Impact on this project

### Critical: `GET /artists/{id}/top-tracks` removed (no replacement)

This is the **core** of the script — `artist_top_tracks()` fetches the top tracks per band.

There is no direct replacement endpoint. Possible workarounds:

1. `GET /artists/{id}/albums` → `GET /albums/{id}/tracks` (pick tracks from recent/popular albums)
2. `GET /search?type=track&q=artist:Name` (search for tracks by artist, but search `limit` is now capped at 10)

Both lose the "top tracks by popularity" ranking since the `popularity` field on tracks is also removed.

### `POST /users/{user_id}/playlists` → `POST /me/playlists`

`create_playlist()` uses `sp.user_playlist_create()` which calls the removed endpoint.

**Fix:** Replace with a call targeting `POST /me/playlists` (needs spotipy update or raw request).

### `GET /playlists/{id}/tracks` → `GET /playlists/{id}/items`

`get_playlist_track_uris()` uses `sp.playlist_tracks()` which calls the removed endpoint.

**Fix:** Use the new `/items` endpoint. Response field renamed: `tracks` → `items`, `track` → `item`.

### `POST /playlists/{id}/tracks` → `POST /playlists/{id}/items`

`add_tracks_in_chunks()` uses `sp.playlist_add_items()` which calls the removed endpoint.

**Fix:** Use `POST /playlists/{id}/items`.

### `PUT /playlists/{id}/tracks` → `PUT /playlists/{id}/items`

`replace_playlist_tracks()` uses `sp.playlist_replace_items()` which calls the removed endpoint.

**Fix:** Use `PUT /playlists/{id}/items`.

### `DELETE /playlists/{id}/followers` removed

`delete_existing_playlists()` uses `sp.current_user_unfollow_playlist()` which calls the removed endpoint.

**Fix:** Use `DELETE /me/library` with the playlist URI.

### `GET /search` limit reduced

Max `limit` reduced from 50 to **10**, default from 20 to **5**.

The default `SPOTIFY_SEARCH_LIMIT=5` is fine. Values above 10 will break.

## Not affected

| Function | Endpoint | Status |
|---|---|---|
| `sp.current_user()` | `GET /me` | Still available |
| `sp.current_user_playlists()` | `GET /me/playlists` | Still available |
| `sp.playlist_upload_cover_image()` | `PUT /playlists/{id}/images` | Still available |
| `sp.search()` | `GET /search` | Still available (limit capped at 10) |

## Development Mode restrictions (March 9, 2026)

- Spotify **Premium** account required
- **1** Client ID per developer
- **Max 5** authorized users per Client ID

## Dependency: spotipy

Most fixes depend on [spotipy](https://github.com/spotipy-dev/spotipy) releasing an update that targets the new endpoints (`/items` instead of `/tracks`, `/me/playlists` for creation, etc.). If spotipy doesn't update in time, raw HTTP calls via `sp._session` or a different client will be needed.
